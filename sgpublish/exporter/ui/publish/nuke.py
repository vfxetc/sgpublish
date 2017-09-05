from __future__ import absolute_import

import tempfile

from uitools.qt import Q

import nuke

from sgpublish.exporter.ui.publish import Widget as Base
from sgpublish import uiutils as ui_utils



class Widget(Base):
    
    def take_full_screenshot(self):
        
        viewer_window = nuke.activeViewer()
        if not viewer_window:
            return
        viewer = viewer_window.node()

        path = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="publish.", delete=False).name
        viewer.capture(path)
        self.setThumbnail(path)



