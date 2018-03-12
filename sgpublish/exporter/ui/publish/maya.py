from __future__ import absolute_import

import contextlib
import os
import tempfile
import subprocess
import functools
import glob
import time
import datetime
import re
import sys

from uitools.qt import Q
import siteconfig

from maya import cmds

import mayatools.playblast
import mayatools.playblast.picker
from mayatools.tickets import ticket_ui_context
from mayatools.units import core as units 

from sgpublish.exporter.ui.publish import Widget as Base
from sgpublish import uiutils as ui_utils
from sgpublish.exporter.maya import get_sound_for_frames, get_current_sound

from .generic import PublishSafetyError


class PlayblastPicker(Q.Widgets.Dialog):

    def __init__(self, parent=None):
        super(PlayblastPicker, self).__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setWindowModality(Q.WindowModal)
        self.setLayout(Q.VBoxLayout())
        
        self.layout().addWidget(Q.Label("Choose an existing playblast:"))
        
        self._picker = mayatools.playblast.picker.Picker()
        self._picker.autoSetMinimumWidth()
        
        self._picker.setMinimumWidth(600)
        self._picker.pathChanged.connect(self._selection_changed)
        self.layout().addWidget(self._picker)
        
        buttons = Q.HBoxLayout()
        self.layout().addLayout(buttons)
        
        self._playblast_button = Q.PushButton("New")
        self._playblast_button.clicked.connect(self._on_playblast)
        self._playblast_button.setSizePolicy(Q.SizePolicy.Fixed, Q.SizePolicy.Fixed)
        buttons.addWidget(self._playblast_button)
        
        buttons.addStretch()
        
        self._cancel_button = Q.PushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel_button)
        self._cancel_button.setSizePolicy(Q.SizePolicy.Fixed, Q.SizePolicy.Fixed)
        
        self._select_button = Q.PushButton("Choose")
        self._select_button.setEnabled(False)
        self._select_button.clicked.connect(self._on_select)
        buttons.addWidget(self._select_button)
        self._select_button.setSizePolicy(Q.SizePolicy.Fixed, Q.SizePolicy.Fixed)
        self.setWindowTitle("Choose a Playblast")

    def _selection_changed(self, path):
        self._select_button.setEnabled(path is not None)
    
    def _on_playblast(self):
        self.hide()
        self.parent().playblast()
    
    def _on_cancel(self):
        self.hide()
    
    def _on_select(self):
        path = self._picker.currentPath()
        if path is not None:
            self.hide()
            # Assume it is jpg.
            self.parent().setFrames(path + '/*.jpg')


class Widget(Base):
    
    beforePlayblast = Q.pyqtSignal()
    afterPlayblast = Q.pyqtSignal()
    viewerClosed = Q.pyqtSignal()
    
    def _setup_ui(self):
        
        super(Widget, self)._setup_ui()
        
        self._playblast = Q.PushButton(ui_utils.icon('silk/pictures', size=12, as_icon=True), "Playblast")
        self._playblast.clicked.connect(self._on_playblast)
        self._movie_layout.addWidget(self._playblast)
        self._playblast.setFixedHeight(self._movie_path.sizeHint().height())
        self._playblast.setFixedWidth(self._playblast.sizeHint().width() + 2)
        
        if not siteconfig.get_bool('FEATURE_SGPUBLISH_MOVIES', True):
            self._playblast.setEnabled(False)

        self._viewer_msgbox = None
        self.viewerClosed.connect(self._on_viewer_closed)
    
    def take_full_screenshot(self):
        
        # Playblast the first screenshot.
        path = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="publish.", delete=False).name
        frame = cmds.currentTime(q=True)
        mayatools.playblast.playblast(
            frame=[frame],
            format='image',
            completeFilename=path,
            viewer=False,
            p=100,
            framePadding=4,
        )
        self.setThumbnail(path)
    
    def _on_movie_browse(self):
        
        existing = str(self._movie_path.text())
        
        res = cmds.fileDialog2(
            dialogStyle=2, # Maya styled.
            caption="Select Movie or First Frame",
            fileFilter='Movie or Frame (*.mov *.exr *.tif *.tiff *.jpg *.jpeg)',
            fileMode=1, # A single existing file.
            startingDirectory=os.path.dirname(existing) if existing else cmds.workspace(query=True, rootDirectory=True)
        )
        
        if res:
            self._movie_path.setText(res[0])
    
    def _on_playblast(self):
        self._picker = PlayblastPicker(self)
        self._picker.show()
    
    def playblast(self):
        
        minTime = cmds.playbackOptions(q=True, minTime=True)
        maxTime = cmds.playbackOptions(q=True, maxTime=True)
        
        scene_name = os.path.splitext(os.path.basename(cmds.file(q=True, sceneName=True)))[0]
        scene_name = scene_name or 'untitled'

        # Assume that we won't be calling this multiple times within 1 second.
        directory = os.path.join(
            '/var/tmp/playblasts',
            scene_name,
            datetime.datetime.utcnow().strftime('%y%m%d_%H%M%S'),
        )
        os.makedirs(directory)
        
        self.beforePlayblast.emit()
        try:
            mayatools.playblast.playblast(
                startTime=minTime,
                endTime=maxTime,
                format='image',
                viewer=False,
                percent=100,
                framePadding=4,
                filename=os.path.join(directory, scene_name),
            )
        finally:
            self.afterPlayblast.emit()
        
        self.setFrames(os.path.join(directory, scene_name + '.####.jpg'))
    
    def setFrames(self, path):
        
        # The easy part.
        super(Widget, self).setFrames(path)
        
        ### Now we open a viewer, and wait for it to close.

        # Resolve globs into ####.
        if '*' in path:
            prefix, postfix = path.split('*', 1)
            paths = glob.glob(path)
            pattern = '%s(.+?)(\d+)%s$' % (re.escape(prefix), re.escape(postfix))
            for found in paths:
                m = re.match(pattern, found)
                if m:
                    path = '%s%s%s%s' % (prefix, m.group(1), '#' * len(m.group(2)), postfix)
                    break
            else:
                raise ValueError('cannot identify length of frame padding', paths[0])

        # Replace #### with %04d for RV.
        rv_style_path = re.sub(r'(#+)', lambda m: '%%0%dd' % len(m.group(1)) , path)

        cmd = ['rv', '[',
            rv_style_path,
            '-fps', str(units.get_fps()),
        ']']

        sound_path = get_sound_for_frames(path) or get_current_sound()
        if sound_path:
            cmd.extend(['-over', '[', sound_path, ']'])

        # Fix for launching rv from Maya on Mac
        # http://www.tweaksoftware.com/static/documentation/rv/current/html/maya_tools_help.html#_osx_maya_2014
        env = dict(os.environ)
        env.pop('QT_MAC_NO_NATIVE_MENUBAR', None)

        print subprocess.list2cmdline(cmd)
        proc = subprocess.Popen(cmd, env=env)

        # Inform the user that we want them to close the viewer before
        # publishing. This is really just to force them to look at it one last
        # time. We don't need to hold a reference to this one.
        self._viewer_msgbox = msgbox = Q.MessageBox(
            Q.MessageBox.Warning,
            'Close Playblast Viewer',
            'Please close the playblast viewer before publishing. It may take'
            ' a few seconds to launch...',
            Q.MessageBox.Ignore,
            self
        )
        msgbox.setWindowModality(Q.WindowModal)
        msgbox.buttonClicked.connect(msgbox.hide)
        msgbox.show()
        
        # On OS X, `mplay` waits for you to close it.
        if sys.platform.startswith('darwin'):
            self._player_waiting_thread = thread = Q.Thread()
            def run():
                proc.wait()
                self.viewerClosed.emit()
            thread.run = run
            thread.start()
        
        # On Linux, it does not.
        else:
            self._player_waiting_timer = timer = Q.Timer()
            timer.singleShot(5000, self.viewerClosed)
    
    def _on_viewer_closed(self):
        if self._viewer_msgbox:
            self._viewer_msgbox.hide()
            self._viewer_msgbox = None

    def export(self, **kwargs):
        with ticket_ui_context(pass_through=PublishSafetyError):
            return self._export(kwargs)

