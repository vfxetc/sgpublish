import functools
import itertools
import os

from uitools.qt import Q

from maya import cmds

from sgfs.ui.picker import presets as picker_presets
from sgfs.ui.picker.nodes.base import Node as BaseNode
from sgfs import SGFS


class ScenePickerNode(BaseNode):

    @staticmethod
    def is_next_node(state):
        if 'maya_scene' in state:
            return False
        if 'self' not in state:
            return False
        if state['self']['type'] != 'PublishEvent':
            return False
        path = state['self'].fetch('sg_path')
        if os.path.exists(path) and os.path.isdir(path):
            return True
        return False

    def fetch_children(self):
        directory = self.state['self']['sg_path']
        file_names = os.listdir(directory)
        file_names = [x for x in file_names if not x.startswith('.')]
        file_names = [x for x in file_names if os.path.splitext(x)[1] in ('.ma', '.mb')]

        for file_name in file_names:
            scene_name = os.path.splitext(file_name)[0]
            yield scene_name, {Q.DisplayRole: scene_name}, {'maya_scene': os.path.join(directory, file_name)}


class Preview(Q.Widgets.Widget):
    
    def __init__(self):
        super(Preview, self).__init__()
        self._pixmaps = {}
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setMinimumWidth(200)
        self.setLayout(Q.VBoxLayout())
        
        self._thumbnail = Q.Label('')
        self._thumbnail.setFrameShape(Q.Frame.StyledPanel)
        self._thumbnail.setFrameShadow(Q.Frame.Raised)
        self.layout().addWidget(self._thumbnail)
        
        form = Q.FormLayout()
        self.layout().addLayout(form)
        
        self._created_by_label = Q.Label()
        form.addRow("<b>By:</b>", self._created_by_label)

        self._created_at_label = Q.Label()
        form.addRow("<b>At:</b>", self._created_at_label)

        self._description_label = Q.Label()
        self._description_label.setWordWrap(True)
        form.addRow("<b>Desc:</b>", self._description_label)

        self._timeRangeLabel = Q.Label()
        form.addRow("<b>Frames:</b>", self._timeRangeLabel)
        
        self.layout().addStretch()
    
    def update(self, entity):
        
        # TODO: Do this async.
        # We're also priming the sg_default_reference_namespace (assuming
        # it exists).
        by, at, desc, _ = entity.fetch((
            'created_by.HumanUser.name',
            'created_at',
            'description',
            'sg_link.Task.entity.Asset.sg_default_reference_namespace',
        ), force=True)
        self._created_by_label.setText(str(by))
        self._created_at_label.setText(str(at.strftime('%y-%m-%d %I:%M %p')))
        self._description_label.setText(str(desc))
        
        sgfs = SGFS(session=entity.session)
        path = sgfs.path_for_entity(entity)
        tags = sgfs.get_directory_entity_tags(path)
        tags = [t for t in tags if t['entity'] is entity]
        tag = tags[0]

        maya_data = tag.get('maya', {})
        time_range = '%s - %s' % (maya_data.get('min_time'), maya_data.get('max_time'))
        self._timeRangeLabel.setText(time_range)
        
        if entity not in self._pixmaps:
            thumbnail_path = tag.get('sgpublish', {}).get('thumbnail') if tags else None
            thumbnail_path = thumbnail_path or os.path.join(path, '.sgfs.thumbnail.jpg')
            if os.path.exists(thumbnail_path):
                pixmap = Q.Pixmap(thumbnail_path)
            else:
                path = os.path.abspath(os.path.join(
                    __file__, '..', '..', '..', '..', 'art', 'no-thumbnail.png'
                ))
                pixmap = Q.Pixmap(path)
            self._pixmaps[entity] = pixmap.scaledToWidth(165, Q.SmoothTransformation)
        
        self._thumbnail.setPixmap(self._pixmaps[entity])
        self._thumbnail.setFixedSize(self._pixmaps[entity].size())

class Dialog(Q.Widgets.Dialog):
    
    def __init__(self, path=None, custom_namespace=True):
        super(Dialog, self).__init__()
        self._node = None
        self._path = path
        self._custom_namespace = custom_namespace
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle("Create Reference")
        
        self.setLayout(Q.VBoxLayout())
        
        workspace = self._path or cmds.workspace(q=True, rootDirectory=True)
        self._model, self._picker = picker_presets.publishes_from_path(workspace)
        self._model.register_node_type(ScenePickerNode)
        self._picker.setMaximumHeight(400)
        self._picker.nodeChanged.connect(self._on_node_changed)
        self._picker.setColumnWidths([200] * 10)
        self.layout().addWidget(self._picker)
        
        button_layout = Q.HBoxLayout()
        bottom_button_layout = Q.HBoxLayout()
        
        self._namespace_field = Q.LineEdit()
        if self._custom_namespace:
            button_layout.addWidget(Q.Label("Namespace:"))
            button_layout.addWidget(self._namespace_field)
        
        button_layout.addStretch()
        self.layout().addLayout(button_layout)
        
        self._button = Q.PushButton("Create Reference")
        self._button.setEnabled(False)
        self._button.clicked.connect(self._on_create_reference)
        
        self._cancel_button = Q.PushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)
        bottom_button_layout.addWidget(self._cancel_button)
        bottom_button_layout.addStretch()
        bottom_button_layout.addWidget(self._button)
      
        self.layout().addLayout(bottom_button_layout)

        self._preview = Preview()
        self._picker.setPreviewWidget(self._preview)
        self._picker.updatePreviewWidget.connect(self._on_update_preview)

    def _on_cancel(self):
        self.close()
    
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
            namespace = publish.get('sg_link.Task.entity.Asset.sg_default_reference_namespace') or publish['code']
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
        
        path = self._node.state.get('maya_scene')
        if not path:
            publish = self._node.state['PublishEvent']
            path = publish.fetch('sg_path')
        
        if self._custom_namespace:

            # Make sure the namespace doesn't already exist
            namespace = str(self._namespace_field.text())
            if namespace in self._existing_namespaces():
                Q.MessageBox.critical(None, 'Namespace Collision',
                    'There is already a reference in the scene with that namespace.'
                )
                return

        else:

            namespace = None
        
        self._do_reference(path, namespace)
        self.hide()

    def _do_reference(self, path, namespace):

        # Reference the file.
        cmds.file(path, reference=True, namespace=namespace)
    
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

