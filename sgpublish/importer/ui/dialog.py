import os
import re

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from .tabs import ImportTabs


class ImportDialog(QtGui.QDialog):
    
    importer = None
    importer_class = None

    def __init__(self, **kwargs):

        for name in ('importer', 'importer_class'):
            if name in kwargs:
                setattr(self, name, kwargs.pop(name))

        super(ImportDialog, self).__init__(**kwargs)

        self.importer_class = self.importer.__class__ if self.importer else self.importer_class
        self.importer = self.importer or self.importer_class()

        self._setup_ui()
    
    def _setup_ui(self):
        
        window_title = re.sub(r'(?<!^)([A-Z])(?![A-Z])', r' \1', self.importer_class.__name__)
        self.setWindowTitle(window_title)

        self.setLayout(QtGui.QVBoxLayout())
        
        self._tabs = ImportTabs()
        self.layout().addWidget(self._tabs)
        
        button = QtGui.QPushButton("Import")
        button.clicked.connect(self._on_import)
        self.layout().addWidget(button)
    
    @property
    def tabs(self):
        return self._tabs

    def _on_import(self, *args):

        tab = self._tabs.currentWidget()
        if hasattr(tab, 'is_ready') and not tab.is_ready():
            QtGui.QMessageBox.critical(self, "Importer Not Ready", "Please make a selection.")
            return

        tab.import_()

        self.close()

