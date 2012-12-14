import functools
import itertools
import os

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs import SGFS
import mayatools.shelf
from mayatools.tickets import ticket_ui_context

from sgpublish import uiutils as ui_utils
from sgpublish import check
from sgpublish.check import maya as maya_check
from sgpublish.mayatools import create_reference


class ReferenceItem(QtGui.QTreeWidgetItem):

    def __init__(self, sgfs, status):

        self.sgfs = sgfs
        self.status = status

        fields = self._setup_data()

        super(ReferenceItem, self).__init__(fields)

        self._setup_ui()

    def _setup_data(self):

        self.path = path = self.status.path
        self.publish = publish = self.status.used

        if publish:
            task = publish.parent()
        else:
            tasks = self.sgfs.entities_from_path(path, 'Task')
            task = tasks[0] if tasks else None

        if task:
            task.fetch(('step.Step.code', 'content'))
            entity = task.parent()
        else:
            entities = self.sgfs.entities_from_path(path, set(('Asset', 'Shot')))
            entity = entities[0] if entities else None

        self.namespace = cmds.file(path, q=True, namespace=True)
        self.node = cmds.referenceQuery(path, referenceNode=True)

        if publish:

            return [
                self.namespace,
                entity['code'],
                task['step.Step.code'],
                task['content'],
                publish['sg_type'],
                publish['code'],
                'COMBOBOX',
            ]

        else:

            return [
                self.namespace,
                entity['code'] if entity else '-',
                task['step.Step.code'] if task else '-',
                task['content'] if task else '-',
                '-',
                '-',
                'BUTTON',
            ]

    def _setup_ui(self):
        
        if self.publish:

            self.combo = combo = QtGui.QComboBox()
            for i, sibling in enumerate(self.status.all):
                combo.addItem('v%04d' % sibling['sg_version'], sibling)
                if sibling['sg_version'] == self.publish['sg_version']:
                    combo.setCurrentIndex(i)
            combo.currentIndexChanged.connect(self._combo_changed)

        else:

            self.button = button = QtGui.QPushButton("Pick a Publish")
            button.clicked.connect(self._pick_publish)

        self._update_icon()

    @property
    def is_latest(self):
        return self.publish is self.status.latest

    def _update_icon(self):
        if self.publish:
            if self.is_latest:
                self.setIcon(0, ui_utils.icon('silk/tick', size=12, as_icon=True))
            else:
                self.setIcon(0, ui_utils.icon('silk/cross', size=12, as_icon=True))
        else:
            self.setIcon(0, ui_utils.icon('silk/error', size=12, as_icon=True))

    def attach_to_tree(self, tree=None):

        if tree:
            self.tree = tree
        
        if self.publish:
            self.tree.setItemWidget(self, 6, self.combo)
        else:
            self.tree.setItemWidget(self, 6, self.button)

    def _combo_changed(self, index):
        with ticket_ui_context():
            new_publish = self.status.all[index]
            new_path = new_publish['sg_path']
            print '#', self.node, 'to', new_path
            cmds.file(
                new_path,
                loadReference=self.node,
                type='mayaAscii' if new_path.endswith('.ma') else 'mayaBinary',
                options='v=0',
            )
            self.publish = new_publish
            self.path = new_path
            self._update_icon()

    def _pick_publish(self):
        self._picker = create_reference.Dialog(path=self.path, custom_namespace=False)
        self._picker._button.setText('Pick a Publish')
        self._picker._do_reference = self._do_picker_reference
        self._picker.show()

    def _do_picker_reference(self, path, namespace):
        with ticket_ui_context():
            print '#', self.node, 'to', path
            cmds.file(
                path,
                loadReference=self.node,
                type='mayaAscii' if path.endswith('.ma') else 'mayaBinary',
                options='v=0',
            )
            self.status = check.check_paths([path])[0]
            # print self.status.used['sg_path']
            # print path
            new_data = self._setup_data()
            for i, v in enumerate(new_data):
                self.setData(i, Qt.DisplayRole, v)
            self._setup_ui()
            self.attach_to_tree()



class Dialog(QtGui.QDialog):
    
    def __init__(self):
        super(Dialog, self).__init__()
        self._setup_ui()
        self._populate_references()
        self._did_check = False
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
            
            item = ReferenceItem(sgfs, reference)
            self._tree.addTopLevelItem(item)
            item.attach_to_tree(self._tree)

        for i in range(7):
            self._tree.resizeColumnToContents(i)
            self._tree.setColumnWidth(i, self._tree.columnWidth(i) + 10)

    def sizeHint(self):
        total = 0
        for i in range(7):
            total += self._tree.columnWidth(i)
        hint = super(Dialog, self).sizeHint()
        hint.setWidth(total + 50)
        return hint

    def closeEvent(self, e):
        super(Dialog, self).closeEvent(e)
        if not self._did_check:
            self._did_check = True
            maya_check.start_background_check()
    

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

