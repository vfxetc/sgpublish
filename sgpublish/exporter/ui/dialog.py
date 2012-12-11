import re

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

import sgpublish.exporter
import sgpublish.exporter.ui.publish
import sgpublish.exporter.ui.tabwidget
import sgpublish.exporter.ui.workarea
import sgpublish.uiutils


class ExporterDialog(QtGui.QDialog):
    
    exporter_class = sgpublish.exporter.Exporter
    
    workarea_tab_class = sgpublish.exporter.ui.tabwidget.Widget
    workarea_kwargs = {}

    publish_tab_class = sgpublish.exporter.ui.publish.Widget

    def __init__(self):
        super(Dialog, self).__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        
        title = re.sub(r'([A-z][^A-Z])', ' \1', self.exporter_class.__name__)
        self.setWindowTitle(title.strip())

        self.setLayout(QtGui.QVBoxLayout())
        self.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed)
        
        self._exporter = self.exporter_class()
        self._exporter_widget = sgpublish.exporter.ui.tabwidget.Widget()
        self.layout().addWidget(self._exporter_widget)
        
        # Work area.
        tab = sgpublish.exporter.ui.workarea.Widget(self._exporter, self.workarea_kwargs)
        self._exporter_widget.addTab(tab, "Export to Work Area")
        
        # SGPublishes.
        tab = sgpublish.exporter.ui.publish.Widget(self._exporter)
        tab.beforeScreenshot.connect(lambda *args: self.hide())
        tab.afterScreenshot.connect(lambda *args: self.show())
        self._exporter_widget.addTab(tab, "Publish to Shotgun")
        
        button_row = QtGui.QHBoxLayout()
        button_row.addStretch()
        self.layout().addLayout(button_row)
        
        self._button = button = QtGui.QPushButton("Export")
        button.clicked.connect(self._on_export)
        button_row.addWidget(button)
        
    def _on_export(self, *args):
        publisher = self._exporter_widget.export()
        if publisher:
            sgpublish.uiutils.announce_publish_success(publisher)
        self.close()

