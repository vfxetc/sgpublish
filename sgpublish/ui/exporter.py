from __future__ import absolute_import

import os
import re
import tempfile
import platform
import subprocess
import traceback

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt

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
        
        self._path_field = QtGui.QLineEdit("NOT YET IMPLEMENTED")
        
        self._browse_button = QtGui.QPushButton("Browse")
        
        self.layout().addLayout(vbox("Export Path", hbox(self._path_field, self._browse_button, spacing=2)))
        
        self._browse_button.setFixedHeight(self._path_field.sizeHint().height())
        self._browse_button.setFixedWidth(self._browse_button.sizeHint().width())


class WorkAreaTab(scene_name.SceneNameWidget):
    
    def __init__(self, kwargs):
        kwargs.setdefault('warning', self._on_warning)
        kwargs.setdefault('error', self._on_error)
        super(WorkAreaTab, self).__init__(kwargs)
    
    def _on_warning(self, msg):
        QtGui.QMessageBox.warning(None, 'Scene Name Warning', msg)
    
    def _on_error(self, msg):
        QtGui.QMessageBox.critical(None, 'Scene Name Error', msg)
        raise ValueError(msg)


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
        
        # Get publish data in the background.
        self.loaded_publishes.connect(self._populate_existing_data)
        self._thread = QtCore.QThread()
        self._thread.run = self._fetch_existing_data
        self._thread.start()
        
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
    
    def version(self):
        return self._version_spinbox.value()
    
    def screenshot_path(self):
        return self._screenshot_path
    
    def export(self):
        
        data = self._task_combo.currentData()
        task = data.get('task')
        if not entity:
            sgfs = SGFS()
            tasks = sgfs.entities_from_path(self._exporter.workspace, 'Task')
            if not tasks:
                raise ValueError('Could not find SGFS tagged entities')
            task = tasks[0]
        
        self._exporter.publish(task, self.name(), self.description(), self.version(), self.screenshot_path())


class Widget(QtGui.QTabWidget):
    
    # Parents should hide on these.
    beforeScreenshot = QtCore.pyqtSignal()
    afterScreenshot = QtCore.pyqtSignal()

    custom_label = "Custom"
    custom_class = CustomTab
    work_area_label = "Work Area"
    work_area_class = WorkAreaTab
    publish_label = "Publish"
    publish_class = PublishTab
    
    def __init__(self, exporter, custom=False, work_area=False, publish=False, work_area_kwargs=None):
        super(Widget, self).__init__()
        
        self._exporter = exporter
        
        self._do_custom = custom
        self._do_work_area = work_area
        self._do_publish = publish
        if not (custom or work_area or publish):
            raise ValueError('must have atleast one tab')
        
        work_area_kwargs = dict(work_area_kwargs or {})
        work_area_kwargs.setdefault('workspace', exporter.workspace)
        work_area_kwargs.setdefault('filename', exporter.filename_hint)
        self._work_area_kwargs = work_area_kwargs
        
        self._setup_ui()
    
    def _setup_ui(self):
        
        # Reset the background of the widgets to the window colour.
        self.setStyleSheet('''
            QTabWidget {
                background-color: palette(window);
            }
        ''')
        
        if self._do_custom:
            self._custom_tab = self.custom_class()
            self.addTab(self._custom_tab, self.custom_label)
        
        if self._do_work_area:
            self._work_area_tab = self.work_area_class(self._work_area_kwargs)
            self.addTab(self._work_area_tab, self.work_area_label)
        
        if self._do_publish:
            self._publish_tab = self.publish_class(self)
            self.addTab(self._publish_tab, self.publish_label)
        
        self.setCurrentIndex(self.count() - 1)
        
        self.currentChanged.connect(self._on_change)
    
    
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
    
    def _on_change(self, *args):
        self.updateGeometry()





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
