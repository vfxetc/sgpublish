import contextlib
import os
import tempfile
import subprocess
import functools

from PyQt4 import QtGui, QtCore

from maya import cmds

from ..publish import Widget as Base
from ... import utils as ui_utils

__also_reload__ = ['...utils', '..publish']


@contextlib.contextmanager
def attr_context(*args, **attrs):
    
    for arg in args:
        attrs.update(arg)
    
    existing = {}
    try:
        for name, value in attrs.iteritems():
            existing[name] = cmds.getAttr(name)
            cmds.setAttr(name, value)
    except:
        for name, value in existing.iteritems():
            cmds.setAttr(name, value)
        raise
    
    yield existing.copy()
    
    for name, value in existing.iteritems():
        cmds.setAttr(name, value)


playblast_attrs = {
    'defaultRenderGlobals.imageFormat': 8,
    'defaultResolution.width': 1280,
    'defaultResolution.height': 720,
    'defaultResolution.deviceAspectRatio': 1.777,
    'defaultResolution.pixelAspect': 1.0,
    'defaultResolution.dotsPerInch': 72,
    'defaultResolution.pixelDensityUnits': 0,
}


def playblast(**kwargs):
    
    current_panel = cmds.getPanel(withFocus=True)
    panel_type = cmds.getPanel(typeOf=current_panel) 
    if panel_type == 'modelPanel':
        cam = cmds.modelPanel(current_panel, q=True, camera=True)
    else:
        cam = None
        cmds.warning('Select a modeling panel to playblast')
    
    if cam:
        displayFilmGate = cmds.camera(cam, q=True, displayFilmGate=True)
        displayResolution = cmds.camera(cam, q=True, displayResolution=True)
        overscan = cmds.camera(cam, q=True, overscan=True)
        camera_attrs = {
            cam + '.horizontalFilmOffset': 0,
            cam + '.verticalFilmOffset': 0,
        }
    else:
        camera_attrs = {}
    
    unit = cmds.currentUnit(q=True, linear=True)
    
    try:
        if cam:
            cmds.camera(cam, edit=True,
                displayFilmGate=0,
                displayResolution=1,
                overscan=1,
            )
        cmds.currentUnit(linear='cm')
        with attr_context(playblast_attrs, camera_attrs):
            cmds.playblast(**kwargs)
        return True
    finally:
        if cam:
            cmds.camera(cam, edit=True,
                displayFilmGate=displayFilmGate,
                displayResolution=displayResolution,
                overscan=overscan,
            )
        cmds.currentUnit(linear=unit)
    
    
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
    
    def take_full_screenshot(self):
        
        # Playblast the first screenshot.
        path = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="publish", delete=False).name
        frame = cmds.currentTime(q=True)
        if playblast(
            frame=[frame],
            format='image',
            completeFilename=path,
            viewer=False,
            p=100,
            framePadding=4,
        ):
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
        
        minTime = cmds.playbackOptions(q=True, minTime=True)
        maxTime = cmds.playbackOptions(q=True, maxTime=True)
        frame_rate = cmds.playbackOptions(q=True, framesPerSecond=True)
        
        directory = tempfile.mkdtemp('playblast.')
        self.beforePlayblast.emit()
        try:
            playblast(
                startTime=minTime,
                endTime=maxTime,
                format='image',
                viewer=False,
                p=100,
                framePadding=4,
                filename=directory + '/frame',
            )
        finally:
            self.afterPlayblast.emit()
        
        # Open a viewer, and wait for it to close.
        proc = subprocess.Popen(['mplay', '-C', '-T', '-R', '-r', str(int(frame_rate)), directory + '/frame.$F4.jpg'])
        self._player_waiter = thread = QtCore.QThread()
        thread.run = functools.partial(self._wait_for_player, proc)
        thread.start()
        
        self._movie_path.setText(directory + '/frame.####.jpg')
        
    
    def _wait_for_player(self, proc):
        proc.wait()
        self.viewerClosed.emit()
        
        
        
