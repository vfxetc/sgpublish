import functools
import itertools
import os
import subprocess

from uitools.qt import Qt, QtCore, QtGui

from maya import cmds

# TODO: Get these out of the key_base!
from ks.core.scene_name.core import SceneName
from ks.core.scene_name.widget import SceneNameWidget

from sgfs.ui.picker import presets as picker_presets
from sgfs.ui.picker.nodes.base import Node as BaseNode
from sgfs import SGFS

from sgpublish import utils


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
            yield scene_name, {Qt.DisplayRole: scene_name}, {'maya_scene': os.path.join(directory, file_name)}


class Preview(QtGui.QWidget):
    
    def __init__(self):
        super(Preview, self).__init__()
        self._pixmaps = {}
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setMinimumWidth(200)
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

        self._timeRangeLabel = QtGui.QLabel()
        form.addRow("<b>Frames:</b>", self._timeRangeLabel)
        
        self.layout().addStretch()
    
    def update(self, entity):
        
        # TODO: Do this async.
        by, at, desc = entity.fetch(('created_by.HumanUser.name', 'created_at', 'description'), force=True)
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
    
    def __init__(self, path=None):
        super(Dialog, self).__init__()
        self._node = None
        self._path = path
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle("Copy Publish to Work Area")
        
        self.setLayout(QtGui.QVBoxLayout())
        
        self._workspace = workspace = self._path or cmds.workspace(q=True, rootDirectory=True)
        self._model, self._picker = picker_presets.publishes_from_path(workspace)
        self._model.register_node_type(ScenePickerNode)
        self._picker.setMaximumHeight(400)
        self._picker.nodeChanged.connect(self._on_node_changed)
        self._picker.setColumnWidths([200] * 10)
        self.layout().addWidget(self._picker)

        self._namer = SceneNameWidget(dict(workspace=workspace))
        self.layout().addWidget(self._namer)
        

        button_layout = QtGui.QHBoxLayout()
        self.layout().addLayout(button_layout)
        

        self._cancel_button = QtGui.QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel_pressed)
        button_layout.addWidget(self._cancel_button)

        button_layout.addStretch()

        self._copy_button = QtGui.QPushButton("Copy")
        self._copy_button.setEnabled(False)
        self._copy_button.clicked.connect(self._on_copy_pressed)
        button_layout.addWidget(self._copy_button)

        self._open_button = QtGui.QPushButton("Copy and Open")
        self._open_button.setEnabled(False)
        self._open_button.clicked.connect(self._on_open_pressed)
        button_layout.addWidget(self._open_button)
        
        self._preview = Preview()
        self._picker.setPreviewWidget(self._preview)
        self._picker.updatePreviewWidget.connect(self._on_update_preview)
        
    def _on_node_changed(self, node):
        
        self._node = node
        self._enable = 'PublishEvent' in node.state
        
        # Button only works when there is a publish.
        self._copy_button.setEnabled(self._enable)
        self._open_button.setEnabled(self._enable)

        if self._enable:
            self._task_path = self._model.sgfs.path_for_entity(node.state['Task'])
        
            publish = node.state.get('PublishEvent')
            
            self._namer._namer.detail = publish['code']
            self._namer._namer.extension = ext = os.path.splitext(publish['sg_path'])[1]
            
            basename = self._namer._namer.get_basename()
            self._namer._namer.revision = utils.get_next_revision(
                os.path.join(self._workspace, 'scenes'),
                os.path.splitext(basename)[0],
                ext,
                1,
            )

            self._namer.namer_updated()
            self._namer.update_preview()

    def _on_update_preview(self, index):
        node = self._model.node_from_index(index)
        entity = node.state['PublishEvent']
        self._preview.update(entity)
    
    def _on_cancel_pressed(self):
        self.hide()

    def _on_open_pressed(self):
        self._on_copy_pressed(open_=True)

    def _on_copy_pressed(self, state=None, open_=False):
        
        src_path = self._node.state.get('maya_scene')
        if not src_path:
            publish = self._node.state['PublishEvent']
            src_path = publish.fetch('sg_path')
        
        dst_path = self._namer._namer.get_path()

        subprocess.call(['cp', src_path, dst_path])
        subprocess.call(['chmod', 'a+w', dst_path])

        self.hide()


        if open_:

            # Make sure they want to proceed if there are changes to the file.
            if cmds.file(q=True, modified=True):
                res = QtGui.QMessageBox.warning(self,
                    "Unsaved Changes",
                    "Would you like to save your changes before opening the copied file?",
                    QtGui.QMessageBox.Save | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel,
                    QtGui.QMessageBox.Save
                )
                if res & QtGui.QMessageBox.Cancel:
                    return
                if res & QtGui.QMessageBox.Save:
                    cmds.file(save=True)

            cmds.file(dst_path, open=True, force=True)


    
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

