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
import functools
import datetime
import itertools

from concurrent.futures import ThreadPoolExecutor

from uitools.qt import Qt, QtCore, QtGui

from maya import cmds

from sgfs import SGFS

from sgpublish import uiutils as ui_utils
from sgpublish import utils
from sgpublish.exporter import maya as io_maya
from sgpublish.exporter.ui.publish import maya as ui_publish
from sgpublish.exporter.ui.publish.generic import PublishSafetyError


def basename(src_path=None):    
    basename = os.path.basename(src_path or cmds.file(q=True, sceneName=True) or 'untitled')
    basename = os.path.splitext(basename)[0]
    basename = re.sub(r'_*[rv]\d+', '', basename)
    return basename


class SceneExporter(io_maya.Exporter):
    
    def __init__(self, **kwargs):
        
        kwargs.setdefault('filename_hint', basename())
        kwargs.setdefault('publish_type', 'maya_scene')
        
        super(SceneExporter, self).__init__(**kwargs)
    
    def export_publish(self, publisher, **kwargs):
        
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
        
        
class PublishWidget(ui_publish.Widget):
    
    def safety_check(self, **kwargs):
        
        if not super(PublishWidget, self).safety_check(**kwargs):
            return False
        
        # Make sure they want to proceed if there are changes to the file.
        if cmds.file(q=True, modified=True):
            res = QtGui.QMessageBox.warning(self,
                "Unsaved Changes",
                "Would you like to save your changes before publishing this"
                " file? The publish will have the changes either way.",
                QtGui.QMessageBox.Save | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel,
                QtGui.QMessageBox.Save
            )
            if res & QtGui.QMessageBox.Cancel:
                return False
            if res & QtGui.QMessageBox.Save:
                cmds.file(save=True)
        
        return True
    
class Dialog(QtGui.QDialog):
    
    def __init__(self, exceptions=None):
        super(Dialog, self).__init__()
        self._setup_ui()
    
    def _setup_ui(self):

        self.setWindowTitle('Scene Publisher')
        self.setLayout(QtGui.QVBoxLayout())

        hbox = QtGui.QHBoxLayout()      

        self._exporter = SceneExporter()
        
        self._publish_widget = PublishWidget(self._exporter)
        self._publish_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self._publish_widget)
        
        self._publish_widget.beforeScreenshot.connect(self.hide)
        self._publish_widget.afterScreenshot.connect(self.show)
        
        cancel_button = QtGui.QPushButton('Cancel')
        cancel_button.clicked.connect(self._on_cancel)
        hbox.addWidget(cancel_button)
        hbox.addStretch()

        publish_button = QtGui.QPushButton('Publish')
        publish_button.clicked.connect(self._on_submit)
        hbox.addWidget(publish_button)
          
        self.layout().addLayout(ui_utils.vbox(hbox))
        self._publish_widget.beforePlayblast.connect(self._before_playblast)
        self._publish_widget.afterPlayblast.connect(self._after_playblast)
        
        self._msgbox = None
    
    def _on_cancel(self):
        self.close()

    def _before_playblast(self):
        self.hide()
    
    def _after_playblast(self):
        self.show()
    
    def _on_submit(self, *args):
        
        # DO IT.
        # This runs the safety check.
        try:
            publisher = self._publish_widget.export()
        except PublishSafetyError:
            return

        # It was an export, instead of a publish.
        if not publisher:
            return
        
        ui_utils.announce_publish_success(
            publisher,
            message="Version {publisher.version} of \"{publisher.name}\" has"
                " been published. Remember to version up!"
        )
        
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
    
    # Be cautious if the scene was never saved
    filename = cmds.file(query=True, sceneName=True)
    if not filename:
        res = QtGui.QMessageBox.warning(None, 'Unsaved Scene', 'This scene has not beed saved. Continue anyways?',
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
            QtGui.QMessageBox.No
        )
        if res & QtGui.QMessageBox.No:
            return
    
    workspace = cmds.workspace(q=True, rootDirectory=True)
    if filename and not filename.startswith(workspace):
        res = QtGui.QMessageBox.warning(None, 'Mismatched Workspace', 'This scene is not from the current workspace. Continue anyways?',
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
            QtGui.QMessageBox.No
        )
        if res & QtGui.QMessageBox.No:
            return
    
    dialog = Dialog()
    dialog.show()

