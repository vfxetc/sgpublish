from PyQt4 import QtGui

from sgpublish.uiutils import vbox, hbox


class Widget(QtGui.QWidget):
    
    def __init__(self, exporter):
        super(CustomTab, self).__init__()
        self._exporter = exporter
        self._setup_ui()
    
    def _setup_ui(self):
        self.setLayout(QtGui.QHBoxLayout())
        
        self._path_field = QtGui.QLineEdit("NOT YET IMPLEMENTED")
        
        self._browse_button = QtGui.QPushButton("Browse")
        
        self.layout().addLayout(vbox("Export Path", hbox(self._path_field, self._browse_button, spacing=2)))
        
        self._browse_button.setFixedHeight(self._path_field.sizeHint().height())
        self._browse_button.setFixedWidth(self._browse_button.sizeHint().width())
    
    def export(self, **kwargs):
        path = str(self._path_field.text())
        return self._exporter.export(os.path.dirname(path), path, **kwargs)

