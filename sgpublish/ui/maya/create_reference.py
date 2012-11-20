import functools
import os

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs.ui.picker import presets as picker_presets
from sgfs import SGFS

__also_reload__ = [
    'sgfs.ui.picker.presets',
]


class Preview(QtGui.QWidget):
    
    def __init__(self):
        super(Preview, self).__init__()
        self._pixmaps = {}
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setLayout(QtGui.QVBoxLayout())
        
        self._thumbnail = QtGui.QLabel('')
        self._thumbnail.setFrameShape(QtGui.QFrame.StyledPanel)
        self._thumbnail.setFrameShadow(QtGui.QFrame.Raised)
        self.layout().addWidget(self._thumbnail)
        
        form = QtGui.QFormLayout()
        self.layout().addLayout(form)
        
        self._created_by_label = QtGui.QLabel()
        form.addRow("<b>By:</b>", self._created_by_label)
        self._created_at_label = QtGui.QLabel()
        form.addRow("<b>At:</b>", self._created_at_label)
        
        self.layout().addStretch()
    
    def update(self, entity):
        
        # Do this async.
        by, at = entity.fetch(('created_by.HumanUser.name', 'created_at'))
        self._created_by_label.setText(str(by))
        self._created_at_label.setText(str(at.strftime('%y-%m-%d %I:%M %p')))
        
        if entity not in self._pixmaps:
            path = os.path.join(SGFS(session=entity.session).path_for_entity(entity), '.sgpublish.thumbnail.jpg')
            if os.path.exists(path):
                pixmap = QtGui.QPixmap(path)
            else:
                path = os.path.abspath(os.path.join(
                    __file__, '..', '..', '..', '..', 'art', 'no-thumbnail.png'
                ))
                pixmap = QtGui.QPixmap(path)
            self._pixmaps[entity] = pixmap.scaledToWidth(165, Qt.SmoothTransformation)
        
        self._thumbnail.setPixmap(self._pixmaps[entity])
        self._thumbnail.setFixedSize(self._pixmaps[entity].size())

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
        
        self._preview = Preview()
        self._picker.setPreviewWidget(self._preview)
        self._picker.updatePreviewWidget.connect(self._on_update_preview)
    
    def _on_node_changed(self, node):
        self._node = node
        self._button.setEnabled('PublishEvent' in node.state)
    
    def _on_update_preview(self, index):
        node = self._model.node_from_index(index)
        entity = node.state['PublishEvent']
        self._preview.update(entity)
        
    def _on_create_reference(self):
        
        publish = self._node.state['PublishEvent']
        name, path = publish.fetch(('code', 'sg_path'))
        
        # Determine which namespaces exist.
        existing = set()
        for ref in cmds.file(q=True, reference=True):
            ns = cmds.file(ref, q=True, namespace=True)
            if ns:
                existing.add(ns)
        
        # Find a name which doesn't clash.
        if name in existing:
            i = 1
            while True:
                indexed_name = '%s_%d' % (name, i)
                if indexed_name not in existing:
                    name = indexed_name
                    break
        
        # Reference the file.
        cmds.file(path, reference=True, namespace=name)
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
    
