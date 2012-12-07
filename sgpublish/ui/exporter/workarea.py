import os

from PyQt4 import QtGui

import sgfs.ui.scene_name.widget as scene_name


class Widget(scene_name.SceneNameWidget):
    
    def __init__(self, exporter, kwargs):
        
        # Copy the kwargs and set some defaults.
        kwargs = dict(kwargs or {})
        kwargs.setdefault('warning', self._on_warning)
        kwargs.setdefault('error', self._on_error)
        kwargs.setdefault('workspace', exporter.workspace)
        kwargs.setdefault('filename', exporter.filename_hint)
        
        super(Widget, self).__init__(kwargs)
        self._exporter = exporter
    
    def _on_warning(self, msg):
        pass
    
    def _on_error(self, msg):
        QtGui.QMessageBox.critical(None, 'Scene Name Error', msg)
        raise ValueError(msg)
    
    def export(self, **kwargs):
        path = self.namer.get_path()
        return self._exporter.export(os.path.dirname(path), path, **kwargs)

