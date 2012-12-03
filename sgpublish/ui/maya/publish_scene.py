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

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

import uifutures
from sgfs import SGFS

from .. import utils as ui_utils
from ... import utils
from ...io import maya as io_maya
from ..exporter.maya import publish as ui_publish
from ...io.maya import get_sound_for_frames, get_current_sound


__also_reload__ = [
    '...io.maya',
    '...utils',
    '..exporter.maya.publish',
    '..utils',
    '..utils',
]


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
        
        # Playblasts should be converted into frames.
        if publisher.frames_path and not publisher.movie_path:
        
            # Put it in the dailies folder.
            # TODO: Do this with SGFS templates.
            project_root = publisher.sgfs.path_for_entity(publisher.link.project())
            movie_directory = os.path.join(
                project_root,
                'VFX_Dailies',
                datetime.datetime.now().strftime('%Y-%m-%d'),
                publisher.link.fetch('step.Step.code') or 'Unknown',
            )
            movie_path = os.path.join(
                movie_directory,
                publisher.name + '_v%04d.mov' % publisher.version,
            )
        
            # Make it unique.
            if os.path.exists(movie_path):
                base, ext = os.path.splitext(movie_path)
                for i in itertools.counter(1):
                    movie_path = '%s_%04d%s' % (base, i, ext)
                    if not os.path.exists(movie_path):
                        break
            
            # Make the folder.
            if not os.path.exists(movie_directory):
                os.makedirs(movie_directory)
            
            sound_path = get_sound_for_frames(publisher.frames_path) or get_current_sound()
            
            # Spawn the job.
            print '# Scheduling make_quicktime to %r from %r' % (movie_path, publisher.frames_path)
            if sound_path:
                print '# Sound from %r' % sound_path
            
            with uifutures.Executor() as executor:
                
                executor.submit_ext(
                    func=utils.make_quicktime,
                    args=(movie_path, publisher.frames_path, sound_path),
                    name="QuickTime \"%s_v%04d\"" % (publisher.name, publisher.version),
                )
                
            
            # Finally set the Shotgun attributes.
            publisher.movie_path = movie_path
            publisher.movie_url = {
                'url': 'http://keyweb' + movie_path,
                'name': os.path.basename(movie_path),
            }
            publisher.frames_path = None
        
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
        
        self._exporter = SceneExporter()
        
        self._publish_widget = ui_publish.Widget(self._exporter)
        self._publish_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self._publish_widget)
        
        self._publish_widget.beforeScreenshot.connect(self.hide)
        self._publish_widget.afterScreenshot.connect(self.show)
        
        button = QtGui.QPushButton('Publish')
        button.clicked.connect(self._on_submit)
        self.layout().addLayout(ui_utils.vbox(button))
        
        self._publish_widget.beforePlayblast.connect(self._before_playblast)
        self._publish_widget.afterPlayblast.connect(self._after_playblast)
        
        self._msgbox = None
    
    def _before_playblast(self):
        self.hide()
    
    def _after_playblast(self):
        self.show()
    
    def _on_submit(self, *args):
        
        # DO IT.
        # This runs the safety check.
        publisher = self._publish_widget.export()
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
    filename = cmds.file(q=True, sceneName=True)
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
        