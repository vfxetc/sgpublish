import os
import tempfile

from PyQt4 import QtGui

from maya import cmds

from ..publish import Widget as Base
from ... import utils as ui_utils

__also_reload__ = ['...utils', '..publish']


class Widget(Base):
    
    def _setup_ui(self):
        
        super(Widget, self)._setup_ui()
        
        self._playblast = QtGui.QPushButton(ui_utils.icon('silk/pictures', as_icon=True), "Playblast")
        self._movie_layout.addWidget(self._playblast)
        self._playblast.setFixedHeight(self._movie_path.sizeHint().height())
        self._playblast.setFixedWidth(self._playblast.sizeHint().width() + 2)
        
        # For dev only!
        self._playblast.setEnabled('KS_DEV_ARGS' in os.environ)
    
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
        self.setThumbnail(path)
