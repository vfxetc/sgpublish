import contextlib
import os
import tempfile
import subprocess
import functools
import glob
import time
import datetime
import re
import platform

from PyQt4 import QtGui, QtCore
Qt = QtCore.Qt

from maya import cmds

import uifutures
import mayatools.playblast

from ..publish import Widget as Base
from ... import utils as ui_utils
from . import sound

__also_reload__ = [
    '...utils',
    '..publish',
    'mayatools.playblast',
    'uifutures',
]


# Calling this too much can lead to "inturrpted system calls". Huh.
platform_system = platform.system()


class PlayblastPicker(QtGui.QDialog):

    def __init__(self, parent):
        super(PlayblastPicker, self).__init__(parent)
        
        self._find_playblasts()
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setWindowModality(Qt.WindowModal)
        self.setLayout(QtGui.QVBoxLayout())
        
        self.layout().addWidget(QtGui.QLabel("Pick an existing playblast:"))
        
        self._tab_widget = QtGui.QTabWidget()
        self._tab_widget.setMinimumWidth(self.parent().sizeHint().width() + 75)
        self._tab_widget.currentChanged.connect(self._selection_changed)
        self.layout().addWidget(self._tab_widget)
        
        
        buttons = QtGui.QHBoxLayout()
        self.layout().addLayout(buttons)
        
        self._playblast_button = QtGui.QPushButton("New")
        self._playblast_button.clicked.connect(self._on_playblast)
        self._playblast_button.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        buttons.addWidget(self._playblast_button)
        
        buttons.addStretch()
        
        self._cancel_button = QtGui.QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel_button)
        self._cancel_button.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        
        self._select_button = QtGui.QPushButton("Open")
        self._select_button.setEnabled(False)
        self._select_button.clicked.connect(self._on_select)
        buttons.addWidget(self._select_button)
        self._select_button.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        
        tabs = {}
        self._items = []
        self._item_widgets = []
        for directory, name, status, frame in sorted(self._playblasts, key=lambda (d, n, s, f): (' None' if s == 'None' else s, n)):
            if status not in tabs:
                tab = QtGui.QListWidget()
                self._tab_widget.addTab(tab, "Playblasts" if status == "None" else status)
                tab.currentTextChanged.connect(self._selection_changed)
                tab.setIconSize(QtCore.QSize(100, 75))
                tabs[status] = tab
            tab = tabs[status]
            
            item = QtGui.QListWidgetItem()
            tab.addItem(item)
            item.setText(name)
            item.setIcon(QtGui.QIcon(frame))
            continue
            widget.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(QtGui.QHBoxLayout())
            thumb = QtGui.QLabel()
            thumb.setPixmap()
            widget.layout().addWidget(thumb)
            widget.layout().addWidget(QtGui.QLabel(name))
            self._items.append(item)
            self._item_widgets.append(widget)
            tab.setItemWidget(item, widget)
        
    
    def _find_playblasts(self):
        self._playblasts = []
        if not os.path.exists('/var/tmp/srv_playblast'):
            return
        for name in os.listdir('/var/tmp/srv_playblast'):
            directory = os.path.join('/var/tmp/srv_playblast', name)
            frames = glob.glob(os.path.join(directory, '*.jpg'))
            if not frames:
                continue
            status_path = os.path.join(directory, 'approval_status')
            status = open(status_path).read() if os.path.exists(status_path) else None
            status = str(status).title()
            self._playblasts.append((directory, name, status, sorted(frames)[0]))
    
    def currentPath(self):
        tab = self._tab_widget.currentWidget()
        item = tab and tab.currentItem()
        name = item and str(item.text())
        path = os.path.join('/var/tmp/srv_playblast', name or '.doesnotexist')
        return path if os.path.exists(path) else None
        
    def _selection_changed(self, *args):
        path = self.currentPath()
        self._select_button.setEnabled(path is not None)
    
    def _on_playblast(self):
        self.hide()
        self.parent().playblast()
    
    def _on_cancel(self):
        self.hide()
    
    def _on_select(self):
        path = self.currentPath()
        if path is not None:
            self.hide()
            self.parent().setFrames(path + '/*.jpg')


class Widget(Base):
    
    beforePlayblast = QtCore.pyqtSignal()
    afterPlayblast = QtCore.pyqtSignal()
    viewerClosed = QtCore.pyqtSignal()
    
    def _setup_ui(self):
        
        super(Widget, self)._setup_ui()
        
        self._playblast = QtGui.QPushButton(ui_utils.icon('silk/pictures', size=12, as_icon=True), "Playblast")
        self._playblast.clicked.connect(self._on_playblast)
        self._movie_layout.addWidget(self._playblast)
        self._playblast.setFixedHeight(self._movie_path.sizeHint().height())
        self._playblast.setFixedWidth(self._playblast.sizeHint().width() + 2)
        
        # For dev only!
        self._playblast.setEnabled('KS_DEV_ARGS' in os.environ)
        
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
                p=100,
                framePadding=4,
                filename=os.path.join(directory, scene_name),
            )
        finally:
            self.afterPlayblast.emit()
        
        self.setFrames(os.path.join(directory, scene_name + '.####.jpg'))
    
    def setFrames(self, path):
        
        # The easy part.
        self._movie_path.setText(path)
        
        # Open a viewer, and wait for it to close.
        sound_path = sound.get_sound_for_frames(path) or sound.get_current_sound()
        frame_rate = cmds.playbackOptions(q=True, framesPerSecond=True)
        houdini_style_path = re.sub(r'(#+)', lambda m: '$F%d' % len(m.group(1)), path)
        cmd = ['mplay', '-C', '-T', '-R', '-r', str(int(frame_rate))]
        if sound_path:
            cmd.extend(('-a', sound_path))
        cmd.append(houdini_style_path)
        proc = subprocess.Popen(cmd)

        # Inform the user that we want them to close the viewer before
        # publishing. This is really just to force them to look at it one last
        # time. We don't need to hold a reference to this one.
        self._viewer_msgbox = msgbox = QtGui.QMessageBox(
            QtGui.QMessageBox.Warning,
            'Close Playblast Viewer',
            'Please close the playblast viewer before publishing. It may take'
            ' a few seconds to launch...',
            QtGui.QMessageBox.Ignore,
            self
        )
        msgbox.setWindowModality(Qt.WindowModal)
        msgbox.buttonClicked.connect(msgbox.hide)
        msgbox.show()
        
        # On OS X, `mplay` waits for you to close it.
        if platform_system == 'Darwin':
            self._player_waiting_thread = thread = QtCore.QThread()
            def run():
                proc.wait()
                self.viewerClosed.emit()
            thread.run = run
            thread.start()
        
        # On Linux, it does not.
        else:
            self._player_waiting_timer = timer = QtCore.QTimer()
            timer.singleShot(5000, self.viewerClosed)
    
    def _on_viewer_closed(self):
        if self._viewer_msgbox:
            self._viewer_msgbox.hide()
            self._viewer_msgbox = None

