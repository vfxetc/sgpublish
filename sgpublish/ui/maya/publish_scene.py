from __future__ import absolute_import

import traceback
import time
import sys
import subprocess
import platform
import tempfile
import os
import re

from concurrent.futures import ThreadPoolExecutor

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs import SGFS

from ...publisher import Publisher

__also_reload__ = [
    '...publisher',
]


class ComboBox(QtGui.QComboBox):
    
    def itemData(self, *args):
        return self._clean_data(super(ComboBox, self).itemData(*args).toPyObject())
    
    def currentData(self):
        return self.itemData(self.currentIndex())
    
    def _clean_data(self, data):
        if isinstance(data, dict):
            return dict(self._clean_data(x) for x in data.iteritems())
        if isinstance(data, (tuple, list)):
            return type(data)(self._clean_data(x) for x in data)
        if isinstance(data, QtCore.QString):
            return unicode(data)
        return data


class VBox(QtGui.QVBoxLayout):
    
    def __init__(self, *args):
        super(VBox, self).__init__()
        self.parts = args
        for arg in args:
            self.addWidget(arg)


class Dialog(QtGui.QDialog):
    
    def __init__(self, exceptions=None):
        super(Dialog, self).__init__()
        self._exception_list = list(exceptions or [])
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setWindowTitle('Scene Publisher')
        self.setMinimumSize(400, 300)
        self.setLayout(QtGui.QVBoxLayout())
        
        basename = os.path.basename(cmds.file(q=True, sceneName=True))
        basename = os.path.splitext(basename)[0]
        basename = re.sub(r'_*[rv]\d+', '', basename)
        
        self._name_box = VBox(QtGui.QLabel('Name of publish stream:'))
        self.layout().addLayout(self._name_box)
        self._name_combo = ComboBox()
        self._name_combo.addItem('Loading...', {'loading': True})
        self._name_combo.addItem('Create new stream...', {'new': True})
        self._name_combo.currentIndexChanged.connect(self._name_changed)
        self._name_box.addWidget(self._name_combo)
        self._name_field = QtGui.QLineEdit(basename)
        self._name_field.hide()
        self._name_box.addWidget(self._name_field)
        
        ThreadPoolExecutor(1).submit(self._populate_name_box).result()
        
        desc_box = VBox(QtGui.QLabel("Describe the changes that you made:"))
        self.layout().addLayout(desc_box)
        self._description = QtGui.QTextEdit('')
        desc_box.addWidget(self._description)
        
        screenshot_box = VBox(QtGui.QLabel("Screenshot (click to select a part of the screen):"))
        self.layout().addLayout(screenshot_box)
        self._screenshot_path = None
        self._screenshot = QtGui.QLabel()
        self._screenshot.setFrameShadow(QtGui.QFrame.Sunken)
        self._screenshot.setFrameShape(QtGui.QFrame.Panel)
        self._screenshot.mouseReleaseEvent = self.take_partial_screenshot
        screenshot_box.addWidget(self._screenshot)
        self.take_full_screenshot()
        
        button = QtGui.QPushButton('Submit')
        button.clicked.connect(self._on_submit)
        self.layout().addLayout(VBox(button))
    
    def _populate_name_box(self):
        sgfs = SGFS()
        workspace = cmds.workspace(query=True, rootDirectory=True)
        tasks = sgfs.entities_from_path(workspace)
        if not tasks:
            cmds.error('No entities in workspace.')
            return
        if any(x['type'] != 'Task' for x in tasks):
            cmds.error('Non-Task entity in workspace.')
            return
        publishes = sgfs.session.find('PublishEvent', [('sg_link.Task.id', 'in') + tuple(x['id'] for x in tasks), ('sg_type', 'is', 'maya_scene')], ['code', 'sg_version'])
        name_to_version = {}
        for publish in publishes:
            name = publish['code']
            name_to_version[name] = max(name_to_version.get(name, 0), publish['sg_version'])
        for name, version in sorted(name_to_version.iteritems()):
            self._name_combo.insertItem(self._name_combo.count() - 1, '%s (v%04d)' % (name, version + 1), {'name': name})
        if 'loading' in self._name_combo.itemData(0):
            if self._name_combo.currentIndex() == 0:
                self._name_combo.setCurrentIndex(1)
            self._name_combo.removeItem(0)
    
    def _name_changed(self, index):
        data = self._name_combo.itemData(index)
        self._name_field.setVisible('new' in data)
        
    def take_full_screenshot(self):
        # Playblast the first screenshot.
        path = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="publish", delete=False).name
        image_format = cmds.getAttr('defaultRenderGlobals.imageFormat')
        cmds.setAttr('defaultRenderGlobals.imageFormat', 8)
        try:
            frame = cmds.currentTime(q=True)
            cmds.playblast(
                frame=[frame],
                format='image',
                completeFilename=path,
                viewer=False,
                p=100,
                framePadding=4,
            )
        finally:
            cmds.setAttr('defaultRenderGlobals.imageFormat', image_format)
        self.setScreenshot(path)
    
    def take_partial_screenshot(self, *args):
        self.hide()
        path = tempfile.NamedTemporaryFile(suffix=".png", prefix="screenshot", delete=False).name
        if platform.system() == "Darwin":
            # use built-in screenshot command on the mac
            proc = subprocess.Popen(['screencapture', '-mis', path])
        else:
            proc = subprocess.Popen(['import', path])
        proc.wait()
        print proc.returncode
        self.show()
        if os.stat(path).st_size:
            self.setScreenshot(path)
    
    def setScreenshot(self, path):
        self._screenshot_path = path
        pixmap = QtGui.QPixmap(path).scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._screenshot.setPixmap(pixmap)
        self._screenshot.setFixedSize(pixmap.size())
    
    def name(self):
        data = self._name_combo.currentData()
        return data.get('name', str(self._name_field.text()))
        
    def description(self):
        return str(self._description.toPlainText())
    
    def _on_submit(self, *args):
        
        sgfs = SGFS()
        entities = sgfs.entities_from_path(cmds.file(q=True, sceneName=True))
        if not entities:
            cmds.error('Could not find SGFS tagged entities')
            return
        
        with Publisher(
            link=entities[0],
            type="maya_scene",
            code=self.name(),
            description=self.description(),
        ) as publish:
            
            # Tag it with the ID.
            # TODO: maintain the old ones.
            cmds.fileInfo('sgpublish_id', str(publish.id))
            
            # Save the file into the directory.
            src_path = cmds.file(q=True, sceneName=True)
            try:
                dst_path = os.path.join(publish.directory, os.path.basename(src_path))
                maya_type = 'mayaBinary' if dst_path.endswith('.mb') else 'mayaAscii'
                cmds.file(rename=dst_path)
                cmds.file(save=True, type=maya_type)
            finally:
                cmds.file(rename=src_path)
            
            # Set the primary path.
            publish.path = dst_path
            
            # Attach a thumbnail.
            publish.thumbnail_path = self._screenshot_path
        
        self.close()
        QtGui.QMessageBox.information(None,
            'Publish Created',
            'Version %d has been created on Shotgun' % publish.version,
        )



def __before_reload__():
    # We have to manually clean this, since we aren't totally sure it will
    # always fall out of scope.
    global dialog
    if dialog:
        dialog.close()
        dialog.destroy()
        dialog = None


dialog = None


def run():
    global dialog
    if dialog:
        dialog.close()
    dialog = Dialog()
    dialog.show()
        