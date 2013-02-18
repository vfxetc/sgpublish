import functools
import itertools
import os

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from maya import cmds

from sgfs import SGFS
import mayatools.shelf
from mayatools.tickets import ticket_ui_context
from mayatools.geocache import utils as geocache_utils

from sgpublish import uiutils as ui_utils
from sgpublish import check
from sgpublish.check import maya as maya_check
from sgpublish.mayatools import create_reference


class VersionedItem(QtGui.QTreeWidgetItem):

    default_type = '-'

    def __init__(self, sgfs, status):

        self.sgfs = sgfs
        self.status = status

        self._setupData()

        fields = self._viewFields()
        super(VersionedItem, self).__init__(fields)

        self._setupGui()

    def _setupData(self):

        self.path = path = self.status.path
        self.name = os.path.basename(self.path)
        self.publish = publish = self.status.used

        if publish:
            task = self.task = publish.parent()
        else:
            tasks = self.sgfs.entities_from_path(path, 'Task')
            task = self.task = tasks[0] if tasks else None

        if task:
            task.fetch(('step.Step.code', 'content'))
            self.entity = task.parent()
        else:
            entities = self.sgfs.entities_from_path(path, set(('Asset', 'Shot')))
            self.entity = entities[0] if entities else None


    def _viewFields(self):

        if self.publish:

            return [
                self.name,
                self.entity['code'],
                self.task['step.Step.code'],
                self.task['content'],
                self.publish['sg_type'],
                self.publish['code'],
                ('v%04d' % self.publish['sg_version']) if self.is_latest else
                ('v%04d (of %d)' % (self.publish['sg_version'], self.status.latest['sg_version'])),
            ]

        else:

            return [
                self.name,
                self.entity['code'] if self.entity else '-',
                self.task['step.Step.code'] if self.task else '-',
                self.task['content'] if self.task else '-',
                self.default_type,
                '-',
                '-',
            ]

    def _setupGui(self):
        self._updateIcon()

    @property
    def is_latest(self):
        return self.publish is self.status.latest

    def _updateIcon(self):
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
        




class ReferenceItem(VersionedItem):

    default_type = 'bare reference'

    def _setupData(self):
        super(ReferenceItem, self)._setupData()

        self.name = self.namespace = cmds.file(self.path, q=True, namespace=True)
        self.node = cmds.referenceQuery(self.path, referenceNode=True)

    def _setupGui(self):
        super(ReferenceItem, self)._setupGui()

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

    def attach_to_tree(self, *args, **kwargs):
        super(ReferenceItem, self).attach_to_tree(*args, **kwargs)
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
            self._updateIcon()

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
            new_data = self._viewFields()
            for i, v in enumerate(new_data):
                self.setData(i, Qt.DisplayRole, v)
            self._setupGui()
            self.attach_to_tree()


class GeocacheItem(VersionedItem):

    default_type = 'bare geocache'

    def _setupData(self):
        super(GeocacheItem, self)._setupData()

        self.name = os.path.basename(os.path.dirname(self.path)) + '/' + os.path.splitext(os.path.basename(self.path))[0]



class Dialog(QtGui.QDialog):
    
    def __init__(self):
        super(Dialog, self).__init__()
        self._setupGui()
        self._populate_references()
        self._did_check = False
        self.setMinimumWidth(self._tree.viewport().width() + 120) # 120 for combos
    
    def _setupGui(self):
        
        self.setWindowTitle("Update References")
        self.setLayout(QtGui.QVBoxLayout())
        
        self._tree = QtGui.QTreeWidget()
        self._tree.setIndentation(0)
        self._tree.setItemsExpandable(False)
        self._tree.setHeaderLabels(["Name", "Entity", "Step", "Task", "Type", "Publish Name", "Version"])
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

        geocaches = geocache_utils.get_existing_cache_mappings().keys()
        geocache_statuses = check.check_paths(geocaches, only_published=True)
        for geocache in geocache_statuses:

            item = GeocacheItem(sgfs, geocache)
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

