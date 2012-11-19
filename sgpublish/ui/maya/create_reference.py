import functools

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs.ui.picker import presets as picker_presets

__also_reload__ = [
    'sgfs.ui.picker.presets',
]


class Dialog(QtGui.QDialog):
    
    def __init__(self):
        super(Dialog, self).__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle("Create Reference")
        
        self.setLayout(QtGui.QVBoxLayout())
        
        workspace = cmds.workspace(q=True, rootDirectory=True)
        self._model, self._picker = picker_presets.publishes_from_path(workspace,
            publish_types=['maya_scene', 'maya_camera'])
        self._picker.setMaximumHeight(400)
        self._picker.nodeChanged = self._on_node_changed
        self.layout().addWidget(self._picker)
        
        button_layout = QtGui.QHBoxLayout()
        button_layout.addStretch()
        self.layout().addLayout(button_layout)
        self._button = QtGui.QPushButton("Create Reference")
        self._button.setEnabled(False)
        self._button.clicked.connect(self._on_create_reference)
        button_layout.addWidget(self._button)
        
        self._preview = QtGui.QLabel('preview')
        self._preview_images = {}
        self._picker.setPreviewWidget(self._preview)
        self._picker.updatePreviewWidget.connect(self._on_update_preview)
    
    def _on_node_changed(self, node):
        self._node = node
        self._button.setEnabled('PublishEvent' in node.state)
    
    def _on_update_preview(self, index):
        node = self._model.node_from_index(index)
        entity = node.state['PublishEvent']
        if entity not in self._preview_images:
            pixmap = QtGui.QPixmap()
            from urllib import urlopen
            pixmap.loadFromData(urlopen(entity.fetch('image')).read())
            self._preview_images[entity] = pixmap.scaledToWidth(200, Qt.SmoothTransformation)
        self._preview.setPixmap(self._preview_images[entity])
        self._preview.setFixedHeight(self._preview_images[entity].height())
        
    def _on_create_reference(self):
        publish = self._node.state['PublishEvent']
        path = publish.fetch('sg_path')
        cmds.file(path, reference=True)
        self.hide()
    
def __before_reload__():
    if dialog:
        dialog.close()

dialog = None

def run():
    
    global dialog
    
    if dialog:
        dialog.close()
    
    dialog = Dialog()    
    dialog.show()
    dialog.raise_()
    
