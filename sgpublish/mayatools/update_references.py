import functools
import itertools
import os

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs import SGFS
import mayatools.shelf


from sgpublish import uiutils as ui_utils
from sgpublish import check
from sgpublish.mayatools import create_reference


class Dialog(QtGui.QDialog):
    
    def __init__(self):
        super(Dialog, self).__init__()
        self._setup_ui()
        self._populate_references()
        
        self.setMinimumWidth(self._tree.viewport().width() + 120) # 120 for combos
    
    def _setup_ui(self):
        
        self.setWindowTitle("Update References")
        self.setLayout(QtGui.QVBoxLayout())
        
        self._tree = QtGui.QTreeWidget()
        self._tree.setIndentation(0)
        self._tree.setItemsExpandable(False)
        self._tree.setHeaderLabels(["Namespace", "Entity", "Step", "Task", "Type", "Name", "Version"])
        self.layout().addWidget(self._tree)
        
        
        button_layout = QtGui.QHBoxLayout()
        button_layout.addStretch()
        
        self._update_button = QtGui.QPushButton('Update All')
        button_layout.addWidget(self._update_button)
        
        self._close_button = QtGui.QPushButton('Close')
        button_layout.addWidget(self._close_button)
        
    
    def _populate_references(self):
        
        sgfs = SGFS()

        reference_statuses = check.check_paths(cmds.file(q=True, reference=True), only_published=False)
        for reference in reference_statuses:
            
            path = reference.path
            publish = reference.used

            if publish:
                task = publish.parent()
            else:
                tasks = sgfs.entities_from_path(path, 'Task')
                task = tasks[0] if tasks else None

            if task:
                task.fetch(('step.Step.code', 'content'))
                entity = task.parent()
            else:
                entities = sgfs.entities_from_path(path, set(('Asset', 'Shot')))
                entity = entities[0] if entities else None

            siblings = reference.all
            
            namespace = cmds.file(path, q=True, namespace=True)
            node = cmds.referenceQuery(path, referenceNode=True)

            if publish:

                item = QtGui.QTreeWidgetItem([
                    namespace,
                    entity['code'],
                    task['step.Step.code'],
                    task['content'],
                    publish['sg_type'],
                    publish['code'],
                    'COMBOBOX',
                ])
                item.setIcon(0, ui_utils.icon('silk/tick' if reference.is_latest else 'silk/cross', size=12, as_icon=True))
                # item.setData(0, Qt.UserRole, {'publish': publish, 'siblings': siblings})
            
            else:

                item = QtGui.QTreeWidgetItem([
                    namespace,
                    entity['code'] if entity else '-',
                    task['step.Step.code'] if task else '-',
                    task['content'] if task else '-',
                    '-',
                    '-',
                    'BUTTON',
                ])
                item.setIcon(0, ui_utils.icon('silk/help', size=12, as_icon=True))

            self._tree.addTopLevelItem(item)

            if publish:

                combo = QtGui.QComboBox()
                for i, sibling in enumerate(siblings):
                    combo.addItem('v%04d' % sibling['sg_version'], sibling)
                    if sibling['sg_version'] == publish['sg_version']:
                        combo.setCurrentIndex(i)
                combo.currentIndexChanged.connect(functools.partial(self._combo_changed, node, siblings))
                self._tree.setItemWidget(item, 6, combo)

            else:

                button = QtGui.QPushButton("Pick a Publish")
                button.clicked.connect(functools.partial(self._pick_publish, path, node))
                self._tree.setItemWidget(item, 6, button)

        
        for i in range(7):
            self._tree.resizeColumnToContents(i)
            self._tree.setColumnWidth(i, self._tree.columnWidth(i) + 10)
    
    def _combo_changed(self, node, publishes, index):
        publish = publishes[index]
        path = publish['sg_path']
        print '#', node, 'to', path
        cmds.file(
            path,
            loadReference=node,
            type='mayaAscii' if path.endswith('.ma') else 'mayaBinary',
            options='v=0',
        )
        #publish.fetch('sg_path'), namespace=namespace, reference=True)
    
    def _pick_publish(self, path, node, *args):
        self._picker = create_reference.Dialog(path=path, custom_namespace=False)
        self._picker._button.setText('Pick a Publish')
        self._picker._do_reference = functools.partial(self._do_picker_reference, node)
        self._picker.show()

    def _do_picker_reference(self, node, path, namespace):
        print '#', node, 'to', path
        cmds.file(
            path,
            loadReference=node,
            type='mayaAscii' if path.endswith('.ma') else 'mayaBinary',
            options='v=0',
        )


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

