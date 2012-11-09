from __future__ import absolute_import

import traceback
import time
import sys
import subprocess
import platform
import tempfile
import os
import re

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs import SGFS

from ...publisher import Publisher

__also_reload__ = [
    '...publisher',
]


class Dialog(QtGui.QDialog):
    
    def __init__(self, exceptions=None):
        super(Dialog, self).__init__()
        self._exception_list = list(exceptions or [])
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle('Scene Publisher')
        self.setMinimumSize(400, 300)
        self.setLayout(QtGui.QFormLayout())
        
        basename = os.path.basename(cmds.file(q=True, sceneName=True))
        basename = os.path.splitext(basename)[0]
        basename = re.sub(r'_*[rv]\d+', '', basename)
        
        self._code_label = QtGui.QLabel("Publish Stream")
        self._code = QtGui.QLineEdit(basename)
        self.layout().addRow(self._code_label, self._code)
        
        self._description = QtGui.QTextEdit('Describe any changes you made.')
        self._description.focusInEvent = lambda *args: self._description.selectAll()
        self.layout().addRow("Description", self._description)
        
        self._screenshot_path = None
        self._screenshot = QtGui.QLabel()
        self._screenshot.setFrameShadow(QtGui.QFrame.Sunken)
        self._screenshot.setFrameShape(QtGui.QFrame.Panel)
        self._screenshot.mouseReleaseEvent = self._on_screenshot
        self.layout().addRow("Screenshot", self._screenshot)
        
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
                # showOrnaments=False,
            )
        finally:
            cmds.setAttr('defaultRenderGlobals.imageFormat', image_format)
        self.setScreenshot(path)
        
        buttons = QtGui.QHBoxLayout()
        self.layout().addRow("", buttons)
        
        # button = QtGui.QPushButton('Add Screenshot')
        # buttons.addWidget(button)
        
        buttons.addStretch()
        
        button = QtGui.QPushButton('Submit')
        button.clicked.connect(self._on_submit)
        buttons.addWidget(button)
        
        self._description.selectAll()
    
    def _on_screenshot(self, *args):
        self.hide()
        path = tempfile.NamedTemporaryFile(suffix=".png", prefix="tanktmp", delete=False).name
        if platform.system() == "Darwin":
            # use built-in screenshot command on the mac
            proc = subprocess.Popen(['screencapture', '-mis', path])
        else:
            proc = subprocess.Popen(['import', path])
        proc.wait()
        self.show()
        self.setScreenshot(path)
    
    def setScreenshot(self, path):
        self._screenshot_path = path
        pixmap = QtGui.QPixmap(path).scaledToHeight(100, Qt.SmoothTransformation)
        self._screenshot.setPixmap(pixmap)
        self._screenshot.setFixedSize(pixmap.size())
    
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
            code=str(self._code.text()),
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
        