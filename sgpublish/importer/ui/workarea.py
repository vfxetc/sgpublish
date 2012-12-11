import os

from PyQt4 import QtGui

from sgfs.ui import product_select


class WorkAreaImporter(QtGui.QWidget):
    
    def __init__(self, importer):
        super(WorkAreaImporter, self).__init__()

        self._importer = importer
        self._selector = product_select.Layout(self)

        self.setLayout(QtGui.QVBoxLayout())
        self.layout().addLayout(self._selector)
    
    @property
    def picker(self):
        return self._selector

    def isReady(self):
        path = self._selector.path()
        return bool(path)

    def import_(self, **kwargs):
        path = self._selector.path()
        return self._importer.import_(path, **kwargs)

    def setPath(self, path):
        return self._selector.setPath(path, allow_partial=True)

