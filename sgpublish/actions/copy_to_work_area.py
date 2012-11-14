import os
import subprocess

from PyQt4 import QtGui

from sgfs import SGFS
import sgfs.ui.picker.presets as picker_presets
import sgfs.ui.picker.utils as picker_utils

from .. import utils


class Dialog(QtGui.QDialog):
    
    def __init__(self, publish):
        super(Dialog, self).__init__()
        
        self._publish = publish
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setWindowTitle("Select Task to Copy To")

        self.setMinimumWidth(800)
        self.setMinimumHeight(400)
        self.setLayout(QtGui.QVBoxLayout())
        
        self._model, self._picker = picker_presets.any_task(entity=self._publish['sg_link'])
        self._picker.setMaximumHeight(400)
        self._picker.setPreviewVisible(False)
        self._picker.nodeChanged = self._on_node_changed
        self.layout().addWidget(self._picker)
        
        self._preview = QtGui.QLineEdit()
        self._preview.setReadOnly(True)
        self.layout().addWidget(self._preview)
        
        button_layout = QtGui.QHBoxLayout()
        button_layout.addStretch()
        self.layout().addLayout(button_layout)
        
        self._cancel_button = QtGui.QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self._cancel_button)
        
        self._copy_button = QtGui.QPushButton("Copy")
        self._copy_button.setDefault(True)
        self._copy_button.clicked.connect(self._on_copy)
        button_layout.addWidget(self._copy_button)
        
        # Trigger a UI update.
        self._on_node_changed(self._picker.currentNode())
    
    def _on_cancel(self):
        exit()
    
    def _on_node_changed(self, node):
        self._node = node
        self._enable = 'Task' in node.state
        
        if self._enable:
            self._task_path = self._model.sgfs.path_for_entity(node.state['Task'])
            if self._task_path is not None and os.path.exists(os.path.join(self._task_path, 'maya', 'workspace.mel')):
                self._dst_path = self._calc_dst_path()
                self._preview.setText(self._dst_path)
            else:
                self._enable = False
                self._preview.setText('Maya workspace does not exist.')
        else:
            self._preview.setText('Select a Task.')
        
        self._copy_button.setEnabled(self._enable)
    
    def _calc_dst_path(self):
        basename, ext = os.path.splitext(os.path.basename(self._publish['sg_path']))
        return utils.get_next_revision_path(
            os.path.join(self._task_path, 'maya', 'scenes'),
            basename,
            ext,
            self._publish['sg_version']
        )
    
    def _on_copy(self):
        subprocess.call(['cp', self._publish['sg_path'], self._dst_path])
        subprocess.call(['chmod', 'a+w', self._dst_path])
        exit()


def run(entity_type, selected_ids, **kwargs):
    
    app = QtGui.QApplication([])
    QtGui.QApplication.setWindowIcon(QtGui.QIcon(os.path.abspath(os.path.join(
        __file__, '..', '..', '..', 'icons', 'fatcow', 'brick_go.png'
    ))))
        
    sgfs = SGFS()
    publish = sgfs.session.merge({'type': entity_type, 'id': selected_ids[0]})
    task, type_, _, _ = publish.fetch(('sg_link', 'sg_type', 'sg_path', 'sg_version'))
    if type_ != 'maya_scene':
        QtGui.QMessageBox.critical(None, 'Unknown Publish Type', 'Cannot process publishes of type %r.' % type_)
        exit(1)
    
    task['step'].fetch_core() # For the picker.
    
    dialog = Dialog(publish)
    dialog.show()
    dialog.raise_()
    exit(app.exec_())

if __name__ == '__main__':
    run('PublishEvent', [55])

