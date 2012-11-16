from __future__ import absolute_import

import os
import re
import tempfile
import platform
import subprocess
import traceback

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

from concurrent.futures import ThreadPoolExecutor

from maya import cmds

import sgfs.ui.scene_name.widget as scene_name
from sgfs import SGFS



def _box(layout, *args):
    for arg in args:
        if isinstance(arg, basestring):
            layout.addWidget(QtGui.QLabel(arg))
        elif isinstance(arg, QtGui.QLayout):
            layout.addLayout(arg)
        else:
            layout.addWidget(arg)
    return layout

hbox = lambda *args, **kwargs: _box(QtGui.QHBoxLayout(**kwargs), *args)
vbox = lambda *args, **kwargs: _box(QtGui.QVBoxLayout(**kwargs), *args)


class ComboBox(QtGui.QComboBox):
    
    def itemData(self, *args):
        return self._clean_data(super(ComboBox, self).itemData(*args).toPyObject())
    
    def currentData(self):
        return self.itemData(self.currentIndex())
    
    def _clean_data(self, data):
        if isinstance(data, dict):
            return dict(self._clean_data(x) for x in data.iteritems())
        if isinstance(data, (tuple, list)):
            return type(data)(self._clean_data(x) for x in data)
        if isinstance(data, QtCore.QString):
            return unicode(data)
        return data


class CustomTab(QtGui.QWidget):
    
    def __init__(self):
        super(CustomTab, self).__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        self.setLayout(QtGui.QHBoxLayout())
        
        self._path_field = QtGui.QLineEdit()
        
        self._browse_button = QtGui.QPushButton("Browse")
        
        self.layout().addLayout(vbox("Export Path", hbox(self._path_field, self._browse_button, spacing=2)))
        
        self._browse_button.setFixedHeight(self._path_field.sizeHint().height())
        self._browse_button.setFixedWidth(self._browse_button.sizeHint().width())


class WorkAreaTab(scene_name.SceneNameWidget):
    pass


class PublishTab(QtGui.QWidget):
    
    # Need a signal to communicate across threads.
    loaded_publishes = QtCore.pyqtSignal(object, object)
    
    def __init__(self, owner):
        super(PublishTab, self).__init__()
        
        self._owner = owner
        
        basename = os.path.basename(cmds.file(q=True, sceneName=True))
        basename = os.path.splitext(basename)[0]
        self._basename = re.sub(r'_*[rv]\d+', '', basename)
        
        self._setup_ui()
    
    def _setup_ui(self):
        
        self.setLayout(QtGui.QVBoxLayout())
        
        self._task_combo = ComboBox()
        self._task_combo.addItem('Loading...', {'loading': True})
        self._task_combo.currentIndexChanged.connect(self._task_changed)
        
        self._name_combo = ComboBox()
        self._name_combo.addItem('Loading...', {'loading': True})
        self._name_combo.addItem('Create new stream...', {'new': True})
        self._name_combo.currentIndexChanged.connect(self._name_changed)
        
        self._name_field = QtGui.QLineEdit(self._basename)
        self._name_field.setEnabled(False)
        
        self._version_spinbox = QtGui.QSpinBox()
        self._version_spinbox.setMinimum(1)
        self._version_spinbox.setMaximum(9999)
        
        self.layout().addLayout(hbox(
            vbox("Task", self._task_combo),
            vbox("Publish Stream", self._name_combo),
        ))
        
        self.layout().addLayout(hbox(
            vbox("Name", self._name_field),
            vbox("Version", self._version_spinbox),
        ))
        
        self.loaded_publishes.connect(self._populate_existing_data)
        future = ThreadPoolExecutor(1).submit(self._fetch_existing_data)
        
        self._description = QtGui.QTextEdit('')
        self._description.setMaximumHeight(100)
        
        self._screenshot_path = None
        self._screenshot = QtGui.QLabel()
        self._screenshot.setFrameShadow(QtGui.QFrame.Sunken)
        self._screenshot.setFrameShape(QtGui.QFrame.Panel)
        self._screenshot.setToolTip("Click to specify part of screen.")
        self._screenshot.mouseReleaseEvent = self.take_partial_screenshot
        
        self.layout().addLayout(hbox(
            vbox("Describe Your Changes", self._description),
            vbox("Screenshot", self._screenshot),
        ))
        
        self.take_full_screenshot()
    
    def _fetch_existing_data(self):
        try:
            sgfs = SGFS()
            workspace = cmds.workspace(query=True, rootDirectory=True)
            print 'workspace', workspace
            tasks = sgfs.entities_from_path(workspace)
            if not tasks:
                cmds.error('No entities in workspace.')
                return
            if any(x['type'] != 'Task' for x in tasks):
                cmds.error('Non-Task entity in workspace.')
                return
            publishes = sgfs.session.find('PublishEvent', [('sg_link.Task.id', 'in') + tuple(x['id'] for x in tasks), ('sg_type', 'is', 'maya_scene')], ['code', 'sg_version'])
            self.loaded_publishes.emit(tasks, publishes)
        except:
            traceback.print_exc()
            self._task_combo.clear()
            self._task_combo.addItem('Loading Error!', {})
            raise
        
    def _populate_existing_data(self, tasks, publishes):
        
        history = cmds.fileInfo('sgpublish_id_history', query=True)
        history = set(int(x.strip()) for x in history[0].split(',')) if history else set()
        
        select = None
        
        for t_i, task in enumerate(tasks):
            name_to_version = {}
            for publish in publishes:
                if publish['sg_link'] is not task:
                    continue
                name = publish['code']
                name_to_version[name] = max(name_to_version.get(name, 0), publish['sg_version'])
                
                if publish['id'] in history:
                    select = t_i, name
            
            self._task_combo.addItem('%s - %s' % task.fetch(('step.Step.short_name', 'content')), {
                'task': task,
                'publishes': name_to_version,
            })
        
        if 'loading' in self._task_combo.itemData(0):
            if self._task_combo.currentIndex() == 0:
                self._task_combo.setCurrentIndex(1)
            self._task_combo.removeItem(0)
        
        if select:
            self._task_combo.setCurrentIndex(select[0])
            for i in xrange(self._name_combo.count()):
                data = self._name_combo.itemData(i)
                if data and data.get('name') == select[1]:
                    self._name_combo.setCurrentIndex(i)
                    break
    
    def _task_changed(self, index):
        data = self._name_combo.currentData()
        if not data:
            return
        was_new = 'new' in data
        self._name_combo.clear()
        data = self._task_combo.currentData() or {}
        
        for name, version in sorted(data.get('publishes', {}).iteritems()):
            self._name_combo.addItem('%s (v%04d)' % (name, version), {'name': name, 'version': version})
        self._name_combo.addItem('Create New Stream...', {'new': True})
        if was_new:
            self._name_combo.setCurrentIndex(self._name_combo.count() - 1)
        else:
            self._name_combo.setCurrentIndex(0)
        
    def _name_changed(self, index):
        data = self._name_combo.itemData(index)
        if not data:
            return
        self._name_field.setEnabled('new' in data)
        self._name_field.setText(data.get('name', self._basename))
        self._version_spinbox.setMinimum(data.get('version', 0) + 1)
        self._version_spinbox.setValue(data.get('version', 0) + 1)
        
    def take_full_screenshot(self):
        # TODO: push this off into the maya-specific exporter
        # Playblast the first screenshot.
        path = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="publish", delete=False).name
        image_format = cmds.getAttr('defaultRenderGlobals.imageFormat')
        cmds.setAttr('defaultRenderGlobals.imageFormat', 8)
        try:
            frame = cmds.currentTime(q=True)
            cmds.playblast(
                frame=[frame],
                format='image',
                completeFilename=path,
                viewer=False,
                p=100,
                framePadding=4,
            )
        finally:
            cmds.setAttr('defaultRenderGlobals.imageFormat', image_format)
        self.setScreenshot(path)
    
    def take_partial_screenshot(self, *args):
        path = tempfile.NamedTemporaryFile(suffix=".png", prefix="screenshot", delete=False).name
        self._owner.beforeScreenshot.emit()
        if platform.system() == "Darwin":
            # use built-in screenshot command on the mac
            proc = subprocess.Popen(['screencapture', '-mis', path])
        else:
            proc = subprocess.Popen(['import', path])
        proc.wait()
        self._owner.afterScreenshot.emit()
        if os.stat(path).st_size:
            self.setScreenshot(path)
    
    def setScreenshot(self, path):
        self._screenshot_path = path
        pixmap = QtGui.QPixmap(path).scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._screenshot.setPixmap(pixmap)
        self._screenshot.setFixedSize(pixmap.size())
    
    def name(self):
        data = self._name_combo.currentData()
        return data.get('name', str(self._name_field.text()))
        
    def description(self):
        return str(self._description.toPlainText())
    
    def _on_submit(self, *args):
        
        # Make sure they want to proceed if there are changes to the file.
        if cmds.file(q=True, modified=True):
            res = QtGui.QMessageBox.warning(self,
                "Unsaved Changes",
                "Would you like to save your changes before publishing this file? The publish will have the changes either way.",
                QtGui.QMessageBox.Save | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel,
                QtGui.QMessageBox.Save
            )
            if res & QtGui.QMessageBox.Save:
                cmds.file(save=True)
            if res & QtGui.QMessageBox.Cancel:
                return
            
        data = self._task_combo.currentData()
        entity = data.get('task')
        if not entity:
            sgfs = SGFS()
            entities = sgfs.entities_from_path(cmds.file(q=True, sceneName=True))
            if not entities:
                cmds.error('Could not find SGFS tagged entities')
                return
            entity = entities[0]
        
        with Publisher(
            link=entity,
            type="maya_scene",
            name=self.name(),
            description=self.description(),
            version=self._version_spinbox.value(),
        ) as publish:
            
            # Record the full history of ids.
            history = cmds.fileInfo('sgpublish_id_history', q=True)
            history = [int(x.strip()) for x in history[0].split(',')] if history else []
            history.append(publish.id)
            cmds.fileInfo('sgpublish_id_history', ','.join(str(x) for x in history))
            
            # Record the name that this is submitted under.
            cmds.fileInfo('sgpublish_name', self.name())
            
            # Save the file into the directory.
            src_path = cmds.file(q=True, sceneName=True)
            src_ext = os.path.splitext(src_path)[1]
            try:
                dst_path = os.path.join(publish.directory, os.path.basename(src_path))
                maya_type = 'mayaBinary' if src_ext == '.mb' else 'mayaAscii'
                cmds.file(rename=dst_path)
                cmds.file(save=True, type=maya_type)
            finally:
                cmds.file(rename=src_path)
            
            # Set the primary path.
            publish.path = dst_path
            
            # Attach the screenshot.
            publish.thumbnail_path = self._screenshot_path
        
        # Version-up the file.
        path = utils.get_next_revision_path(os.path.dirname(src_path), self._basename, src_ext, publish.version + 1)
        cmds.file(rename=path)
        # cmds.file(save=True, type=maya_type)
        
        self.close()
        
        # Inform the user, and open the detail page if asked.
        res = QtGui.QMessageBox.information(self,
            'Publish Created',
            'Version %d has been created on Shotgun, and your file has been renamed to %s.' % (publish.version, os.path.basename(path)),
            QtGui.QMessageBox.Open | QtGui.QMessageBox.Ok,
            QtGui.QMessageBox.Ok
        )
        if res & QtGui.QMessageBox.Open:
            if platform.system() == 'Darwin':
                subprocess.call(['open', publish.entity.url])
            else:
                subprocess.call(['xdg-open', publish.entity.url])


class Widget(QtGui.QTabWidget):
    
    # Parents should hide on these.
    beforeScreenshot = QtCore.pyqtSignal()
    afterScreenshot = QtCore.pyqtSignal()

    custom_tab_label = "Custom"
    custom_tab_class = CustomTab
    work_area_tab_label = "Work Area"
    work_area_tab_class = WorkAreaTab
    publish_tab_label = "Publish"
    publish_tab_class = PublishTab
    
    def __init__(self):
        super(Widget, self).__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        
        # Reset the background of the widgets to the window colour.
        self.setStyleSheet('''
            QTabWidget {
                background-color: palette(window);
            }
        ''')
        
        self._custom_tab = self.custom_tab_class()
        self.addTab(self._custom_tab, self.custom_tab_label)
        self._work_area_tab = self.work_area_tab_class()
        self.addTab(self._work_area_tab, self.work_area_tab_label)
        self._publish_tab = self.publish_tab_class(self)
        self.addTab(self._publish_tab, self.publish_tab_label)
        
        self.setCurrentIndex(2)
        
        self.currentChanged.connect(self._on_tab_change)
        
        return
        
        
        box = QtGui.QWidget()
        box.setLayout(QtGui.QVBoxLayout())
        tabs.addTab(box, "Export")
        self._scene_name = scene_name.SceneNameWidget({
            'directory': 'scenes/camera',
            'sub_directory': '',
            'extension': '.ma',
            'workspace': cmds.workspace(q=True, fullName=True) or None,
            'filename': cmds.file(q=True, sceneName=True) or None,
            'warning': self._warning,
            'error': self._warning,
        })
        box.layout().addWidget(self._scene_name)
        
        
        box = QtGui.QWidget()
        tabs.addTab(box, "Publish")
        box.setLayout(QtGui.QVBoxLayout())
        label = QtGui.QLabel("NOT YET IMPLEMENTED")
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        box.layout().addWidget(label)
        
        button_row = QtGui.QHBoxLayout()
        button_row.addStretch()
        self.layout().addLayout(button_row)
        
        self._button = button = QtGui.QPushButton("Export")
        button.clicked.connect(self._on_export)
        button_row.addWidget(button)
        
        self._populate_cameras()
    
    def sizeHint(self):
        
        bar = self.tabBar()
        widget = self.currentWidget()
        
        hint = widget.sizeHint()
        hint.setHeight(hint.height() + bar.sizeHint().height())
        
        for i in xrange(self.count()):
            hint.setWidth(max(hint.width(), self.widget(i).sizeHint().width()))
        
        return hint
    
    def minimumSizeHint(self):
        return self.sizeHint()
    
    def _on_tab_change(self, *args):
        self.updateGeometry()
    
    def _on_reload(self, *args):
        self._populate_cameras()
    
    def _populate_cameras(self):
        previous = str(self._cameras.currentText())
        selection = set(cmds.ls(sl=True, type='transform') or ())
        self._cameras.clear()
        for camera in cmds.ls(type="camera"):
            transform = cmds.listRelatives(camera, parent=True)[0]
            self._cameras.addItem(transform, (transform, camera))
            if (previous and previous == transform) or (not previous and transform in selection):
                self._cameras.setCurrentIndex(self._cameras.count() - 1)
        self._update_status()
    
    def _on_cameras_changed(self, *args):
        self._update_status()
    
    def _nodes_to_export(self):
        
        transform = str(self._cameras.currentText())
        export = set(cmds.listRelatives(transform, allDescendents=True) or ())
        
        parents = [transform]
        while parents:
            parent = parents.pop(0)
            if parent in export:
                continue
            export.add(parent)
            parents.extend(cmds.listRelatives(parent, allParents=True) or ())
        
        return export
        
    def _update_status(self):
        
        counts = {}
        for node in self._nodes_to_export():
            type_ = cmds.nodeType(node)
            counts[type_] = counts.get(type_, 0) + 1
        
        self._summary.setText('\n'.join('%dx %s' % (c, n) for n, c in sorted(counts.iteritems())))
        
    def _on_export(self, *args):
        
        path = self._scene_name._namer.get_path()
        export_path = path
        print path
        
        dir_name = os.path.dirname(path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            
        # If this is 2013 then export to somewhere temporary.
        maya_version = int(mel.eval('about -version').split()[0])
        if maya_version > 2011:
            export_path = os.path.splitext(path)[0] + ('.%d.ma' % maya_version)
        
        # Reset camera settings.
        camera = self._cameras.itemData(self._cameras.currentIndex()).toPyObject()[1]
        original_zoom = tuple(cmds.getAttr(camera + '.' + attr) for attr in ('horizontalFilmOffset', 'verticalFilmOffset', 'overscan'))
        cmds.setAttr(camera + '.horizontalFilmOffset', 0)
        cmds.setAttr(camera + '.verticalFilmOffset', 0)
        cmds.setAttr(camera + '.overscan', 1)
        
        original_selection = cmds.ls(sl=True)
        cmds.select(list(self._nodes_to_export()), replace=True)
        
        cmds.file(export_path, type='mayaAscii', exportSelected=True)
        
        # Rewrite the file to work with 2011.
        if maya_version > 2011:
            downgrade.downgrade_to_2011(export_path, path)
        
        # Restore camera settings.
        cmds.setAttr(camera + '.horizontalFilmOffset', original_zoom[0])
        cmds.setAttr(camera + '.verticalFilmOffset', original_zoom[1])
        cmds.setAttr(camera + '.overscan', original_zoom[2])
        
        # Restore selection.
        if original_selection:
            cmds.select(original_selection, replace=True)
        else:
            cmds.select(clear=True)
        
        self.close()
        
    def _warning(self, message):
        cmds.warning(message)

    def _error(self, message):
        cmds.confirmDialog(title='Scene Name Error', message=message, icon='critical')
        cmds.error(message)


def __before_reload__():
    if dialog:
        dialog.close()

dialog = None

def run():
    
    global dialog
    
    if dialog:
        dialog.close()
    
    dialog = PublishTab()    
    dialog.show()
