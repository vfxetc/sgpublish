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

from .. import utils as ui_utils
from ... import utils
from ...io import maya as io_maya
from ..exporter.maya import publish as ui_publish

__also_reload__ = [
    '...io.maya',
    '..utils',
    '...utils',
    '..exporter.maya.publish',
    '..utils',
]


def basename(src_path=None):    
    basename = os.path.basename(src_path or cmds.file(q=True, sceneName=True))
    basename = os.path.splitext(basename)[0]
    basename = re.sub(r'_*[rv]\d+', '', basename)
    return basename
    
class SceneExporter(io_maya.Exporter):
    
    def __init__(self, **kwargs):
        
        kwargs.setdefault('filename_hint', basename())
        kwargs.setdefault('publish_type', 'maya_scene')
        
        super(SceneExporter, self).__init__(**kwargs)
        
    def export_publish(self, publisher):
        
        # Save the file into the directory.
        src_path = cmds.file(q=True, sceneName=True)
        src_ext = os.path.splitext(src_path)[1]
        try:
            dst_path = os.path.join(publisher.directory, os.path.basename(src_path))
            maya_type = 'mayaBinary' if src_ext == '.mb' else 'mayaAscii'
            cmds.file(rename=dst_path)
            cmds.file(save=True, type=maya_type)
        finally:
            cmds.file(rename=src_path)
            
        # Set the primary path.
        publisher.path = dst_path


class Dialog(QtGui.QDialog):
    
    def __init__(self, exceptions=None):
        super(Dialog, self).__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setWindowTitle('Scene Publisher')
        self.setLayout(QtGui.QVBoxLayout())
        
        self._exporter = SceneExporter()
        
        self._publish_widget = ui_publish.Widget(self._exporter)
        self._publish_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self._publish_widget)
        
        self._publish_widget.beforeScreenshot.connect(self.hide)
        self._publish_widget.afterScreenshot.connect(self.show)
        
        button = QtGui.QPushButton('Publish')
        button.clicked.connect(self._on_submit)
        self.layout().addLayout(ui_utils.vbox(button))
    
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
        
        # DO IT
        publisher = self._publish_widget.export()
        
        # Version-up the file.
        src_path = cmds.file(q=True, sceneName=True)
        new_path = utils.get_next_revision_path(os.path.dirname(src_path), basename(src_path), os.path.splitext(src_path)[1], publisher.version + 1)
        cmds.file(rename=new_path)
        # cmds.file(save=True, type=maya_type)
        
        ui_utils.announce_publish_success(publisher)
        self.close()



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
        