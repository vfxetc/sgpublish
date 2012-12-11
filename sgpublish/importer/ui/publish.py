from __future__ import absolute_import

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from sgfs.ui.picker import presets as picker_presets


class PublishImporter(QtGui.QWidget):

    def __init__(self, importer, publish_type):
        super(PublishImporter, self).__init__()
        self._importer = importer
        self._publish_type = publish_type

        self._setup_ui()

    def _setup_ui(self):

        self.setLayout(QtGui.QVBoxLayout())

        self._model, self._picker = picker_presets.publishes_from_path(
            self._importer.workspace,
            publish_types=['maya_camera'],
        )
        self._picker.setMaximumHeight(150)
        self._picker.setColumnWidths([150] * 10)
        self._picker.setMaximumWidth(150 * 4 + 2)
        self._picker.setPreviewVisible(False)
        self.layout().addWidget(self._picker)

    def setPath(self, path):
        pass

    def isReady(self):
        data = self._picker.currentState()
        return 'PublishEvent' in (data or {})

    def import_(self):
        publish = self._picker.currentState()['PublishEvent']
        self._importer.import_publish(publish)
    
