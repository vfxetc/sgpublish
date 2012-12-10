import functools
import itertools
import os

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs.ui.picker import presets as picker_presets
from sgfs import SGFS


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
        self._description_label = QtGui.QLabel()
        self._description_label.setWordWrap(True)
        form.addRow("<b>Desc:</b>", self._description_label)
        
        self.layout().addStretch()
    
    def update(self, entity):
        
        # Do this async.
        by, at, desc = entity.fetch(('created_by.HumanUser.name', 'created_at', 'description'))
        self._created_by_label.setText(str(by))
        self._created_at_label.setText(str(at.strftime('%y-%m-%d %I:%M %p')))
        self._description_label.setText(str(desc))
        
        if entity not in self._pixmaps:
            sgfs = SGFS(session=entity.session)
            path = sgfs.path_for_entity(entity)
            tags = sgfs.get_directory_entity_tags(path)
            tags = [t for t in tags if t['entity'] is entity]
            thumbnail_path = tags[0].get('sgpublish', {}).get('thumbnail') if tags else None
            thumbnail_path = thumbnail_path or os.path.join(path, '.sgfs.thumbnail.jpg')
            if os.path.exists(thumbnail_path):
                pixmap = QtGui.QPixmap(thumbnail_path)
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
        self._node = None
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle("Create Reference")
        
        self.setLayout(QtGui.QVBoxLayout())
        
        workspace = cmds.workspace(q=True, rootDirectory=True)
        self._model, self._picker = picker_presets.publishes_from_path(workspace)
        self._picker.setMaximumHeight(400)
        self._picker.nodeChanged = self._on_node_changed
        self.layout().addWidget(self._picker)
        
        button_layout = QtGui.QHBoxLayout()
        
        self._namespace_field = QtGui.QLineEdit()
        button_layout.addWidget(QtGui.QLabel("Namespace:"))
        button_layout.addWidget(self._namespace_field)
        
        button_layout.addStretch()
        self.layout().addLayout(button_layout)
        self._button = QtGui.QPushButton("Create Reference")
        self._button.setEnabled(False)
        self._button.clicked.connect(self._on_create_reference)
        button_layout.addWidget(self._button)
        
        self._preview = Preview()
        self._picker.setPreviewWidget(self._preview)
        self._picker.updatePreviewWidget.connect(self._on_update_preview)
    
    def _existing_namespaces(self):
        existing = set()
        for ref in cmds.file(q=True, reference=True):
            namespace = cmds.file(ref, q=True, namespace=True)
            if namespace:
                existing.add(namespace)
        return existing
        
    def _on_node_changed(self, node):
        
        # Button only works when there is a publish.
        self._button.setEnabled('PublishEvent' in node.state)
        
        last_publish = self._node and self._node.state.get('PublishEvent')
        publish = node.state.get('PublishEvent')
        if publish and (last_publish is None or 
                        last_publish['sg_link'] is not publish['sg_link'] or
                        last_publish['code'] != publish['code']
        ):
            
            # Find a name which doesn't clash.
            namespace = publish['code']
            existing = self._existing_namespaces()
            if namespace in existing:
                for i in itertools.count(1):
                    indexed_name = '%s_%d' % (namespace, i)
                    if indexed_name not in existing:
                        namespace = indexed_name
                        break
            
            self._namespace_field.setText(namespace)
        
        self._node = node
        
        
    
    def _on_update_preview(self, index):
        node = self._model.node_from_index(index)
        entity = node.state['PublishEvent']
        self._preview.update(entity)
        
    def _on_create_reference(self):
        
        publish = self._node.state['PublishEvent']
        path = publish.fetch('sg_path')
        
        # Make sure the namespace doesn't already exist
        namespace = str(self._namespace_field.text())
        if namespace in self._existing_namespaces():
            QtGui.QMessageBox.critical(None, 'Namespace Collision',
                'There is already a reference in the scene with that namespace.'
            )
            return
        
        # Reference the file.
        cmds.file(path, reference=True, namespace=namespace)
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

