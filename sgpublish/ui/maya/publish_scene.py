from __future__ import absolute_import

import traceback
import time
import sys
import subprocess
import platform
import tempfile
import os
import re
import glob

from concurrent.futures import ThreadPoolExecutor

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs import SGFS

from ...publisher import Publisher
from ... import utils

__also_reload__ = [
    '...publisher',
    '...utils',
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
    
    # Need a signal to communicate across threads.
    loaded_publishes = QtCore.pyqtSignal(object, object)
    
    def __init__(self, exceptions=None):
        super(Dialog, self).__init__()
        self._exception_list = list(exceptions or [])
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setWindowTitle('Scene Publisher')
        self.setMinimumSize(600, 400)
        self.setLayout(QtGui.QVBoxLayout())
        
        basename = os.path.basename(cmds.file(q=True, sceneName=True))
        basename = os.path.splitext(basename)[0]
        self._basename = re.sub(r'_*[rv]\d+', '', basename)
        
        self._name_box = VBox(QtGui.QLabel('Task and Name of publish stream:'))
        self.layout().addLayout(self._name_box)
        combo_layout = QtGui.QHBoxLayout()
        self._name_box.addLayout(combo_layout)
        name_layout = QtGui.QHBoxLayout()
        self._name_box.addLayout(name_layout)
        
        self._task_combo = ComboBox()
        self._task_combo.addItem('Loading...', {'loading': True})
        self._task_combo.currentIndexChanged.connect(self._task_changed)
        combo_layout.addWidget(self._task_combo)
        self._name_combo = ComboBox()
        self._name_combo.addItem('Loading...', {'loading': True})
        self._name_combo.addItem('Create new stream...', {'new': True})
        self._name_combo.currentIndexChanged.connect(self._name_changed)
        combo_layout.addWidget(self._name_combo)
        self._name_field = QtGui.QLineEdit(self._basename)
        self._name_field.setEnabled(False)
        name_layout.addWidget(self._name_field)
        self._version_spinbox = QtGui.QSpinBox()
        self._version_spinbox.setMinimum(1)
        self._version_spinbox.setMaximum(9999)
        name_layout.addWidget(self._version_spinbox)
        
        self.loaded_publishes.connect(self._populate_existing_data)
        future = ThreadPoolExecutor(1).submit(self._fetch_existing_data)
        
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
    
    def _fetch_existing_data(self):
        try:
            sgfs = SGFS()
            workspace = cmds.workspace(query=True, rootDirectory=True)
            print 'workspace', workspace
            tasks = sgfs.entities_from_path(workspace)
            if not tasks:
                cmds.error('No entities in workspace.')
                return
            if any(x['type'] != 'Task' for x in tasks):
                cmds.error('Non-Task entity in workspace.')
                return
            publishes = sgfs.session.find('PublishEvent', [('sg_link.Task.id', 'in') + tuple(x['id'] for x in tasks), ('sg_type', 'is', 'maya_scene')], ['code', 'sg_version'])
            self.loaded_publishes.emit(tasks, publishes)
        except:
            traceback.print_exc()
            self._task_combo.clear()
            self._task_combo.addItem('Loading Error!', {})
            raise
        
    def _populate_existing_data(self, tasks, publishes):
        
        history = cmds.fileInfo('sgpublish_id_history', query=True)
        history = set(int(x.strip()) for x in history[0].split(',')) if history else set()
        
        select = None
        
        for t_i, task in enumerate(tasks):
            name_to_version = {}
            for publish in publishes:
                if publish['sg_link'] is not task:
                    continue
                name = publish['code']
                name_to_version[name] = max(name_to_version.get(name, 0), publish['sg_version'])
                
                if publish['id'] in history:
                    select = t_i, name
            
            self._task_combo.addItem('%s - %s' % task.fetch(('step.Step.short_name', 'content')), {
                'task': task,
                'publishes': name_to_version,
            })
        
        if 'loading' in self._task_combo.itemData(0):
            if self._task_combo.currentIndex() == 0:
                self._task_combo.setCurrentIndex(1)
            self._task_combo.removeItem(0)
        
        if select:
            self._task_combo.setCurrentIndex(select[0])
            for i in xrange(self._name_combo.count()):
                data = self._name_combo.itemData(i)
                if data and data.get('name') == select[1]:
                    self._name_combo.setCurrentIndex(i)
                    break
    
    def _task_changed(self, index):
        data = self._name_combo.currentData()
        if not data:
            return
        was_new = 'new' in data
        self._name_combo.clear()
        data = self._task_combo.currentData() or {}
        
        for name, version in sorted(data.get('publishes', {}).iteritems()):
            self._name_combo.addItem('%s (v%04d)' % (name, version), {'name': name, 'version': version})
        self._name_combo.addItem('Create New Stream...', {'new': True})
        if was_new:
            self._name_combo.setCurrentIndex(self._name_combo.count() - 1)
        else:
            self._name_combo.setCurrentIndex(0)
        
    def _name_changed(self, index):
        data = self._name_combo.itemData(index)
        if not data:
            return
        self._name_field.setEnabled('new' in data)
        self._name_field.setText(data.get('name', self._basename))
        self._version_spinbox.setMinimum(data.get('version', 0) + 1)
        self._version_spinbox.setValue(data.get('version', 0) + 1)
        
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
        
        # Make sure they want to proceed if there are changes to the file.
        if cmds.file(q=True, modified=True):
            res = QtGui.QMessageBox.warning(self,
                "Unsaved Changes",
                "Would you like to save your changes before publishing this file? The publish will have the changes either way.",
                QtGui.QMessageBox.Save | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel,
                QtGui.QMessageBox.Save
            )
            if res & QtGui.QMessageBox.Save:
                cmds.file(save=True)
            if res & QtGui.QMessageBox.Cancel:
                return
            
        data = self._task_combo.currentData()
        entity = data.get('task')
        if not entity:
            sgfs = SGFS()
            entities = sgfs.entities_from_path(cmds.file(q=True, sceneName=True))
            if not entities:
                cmds.error('Could not find SGFS tagged entities')
                return
            entity = entities[0]
        
        with Publisher(
            link=entity,
            type="maya_scene",
            name=self.name(),
            description=self.description(),
            version=self._version_spinbox.value(),
        ) as publish:
            
            # Record the full history of ids.
            history = cmds.fileInfo('sgpublish_id_history', q=True)
            history = [int(x.strip()) for x in history[0].split(',')] if history else []
            history.append(publish.id)
            cmds.fileInfo('sgpublish_id_history', ','.join(str(x) for x in history))
            
            # Record the name that this is submitted under.
            cmds.fileInfo('sgpublish_name', self.name())
            
            # Save the file into the directory.
            src_path = cmds.file(q=True, sceneName=True)
            src_ext = os.path.splitext(src_path)[1]
            try:
                dst_path = os.path.join(publish.directory, os.path.basename(src_path))
                maya_type = 'mayaBinary' if src_ext == '.mb' else 'mayaAscii'
                cmds.file(rename=dst_path)
                cmds.file(save=True, type=maya_type)
            finally:
                cmds.file(rename=src_path)
            
            # Set the primary path.
            publish.path = dst_path
            
            # Attach the screenshot.
            publish.thumbnail_path = self._screenshot_path
        
        # Version-up the file.
        path = utils.get_next_revision_path(os.path.dirname(src_path), self._basename, src_ext, publish.version + 1)
        cmds.file(rename=path)
        # cmds.file(save=True, type=maya_type)
        
        self.close()
        
        # Inform the user, and open the detail page if asked.
        res = QtGui.QMessageBox.information(self,
            'Publish Created',
            'Version %d has been created on Shotgun, and your file has been renamed to %s.' % (publish.version, os.path.basename(path)),
            QtGui.QMessageBox.Open | QtGui.QMessageBox.Ok,
            QtGui.QMessageBox.Ok
        )
        if res & QtGui.QMessageBox.Open:
            if platform.system() == 'Darwin':
                subprocess.call(['open', publish.entity.url])
            else:
                subprocess.call(['xdg-open', publish.entity.url])



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
    
    # Make sure the file was saved once.
    # TODO: Remove this restriction eventually.
    filename = cmds.file(q=True, sceneName=True)
    if not filename:
        QtGui.QMessageBox.warning(None, 'Unsaved Scene', 'The scene must be saved once before it can be published.')
        return
    
    workspace = cmds.workspace(q=True, rootDirectory=True)
    if not filename.startswith(workspace):
        res = QtGui.QMessageBox.warning(None, 'Mismatched Workspace', 'This scene is not from the current workspace. Continue anyways?',
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
            QtGui.QMessageBox.No
        )
        if res & QtGui.QMessageBox.No:
            return
    
    dialog = Dialog()
    dialog.show()
        