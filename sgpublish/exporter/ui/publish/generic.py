from __future__ import absolute_import

import functools
import os
import re
import sys
import tempfile
import traceback
import subprocess
import datetime

from uitools.qt import Qt, QtCore, QtGui
import siteconfig

from sgfs import SGFS
from sgactions.ticketui import ticket_ui_context

from sgpublish.uiutils import ComboBox, hbox, vbox, icon


class PublishSafetyError(RuntimeError):
    pass


class TimeSpinner(QtGui.QSpinBox):
    
    def __init__(self):
        super(TimeSpinner, self).__init__(
            singleStep=15,
            maximum=60*8*5,
        )
    
    def textFromValue(self, value):
        return '%d:%02d' % (value / 60, value % 60)
    
    def valueFromText(self, text, strict=False):
        m = re.match('(\d+):(\d{,2})', text)
        if m:
            return 60 * int(m.group(1)) + int(m.group(2) or 0)
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return int(60 * float(text))
        except ValueError:
            pass
        
        if strict:
            return None
        else:
            return 0
    
    def validate(self, text, pos):
        if self.valueFromText(text) is not None:
            return QtGui.QValidator.Acceptable, pos
        else:
            return QtGui.QValidator.Invalid, pos
    


class Widget(QtGui.QWidget):
    
    # Windows should hide on these.
    beforeScreenshot = QtCore.Signal()
    afterScreenshot = QtCore.Signal()
    
    # Need a signal to communicate across threads.
    loaded_publishes = QtCore.Signal(object, object)
    
    def __init__(self, exporter):
        super(Widget, self).__init__()
        
        self._exporter = exporter

        self._existing_streams = set()
        
        basename = os.path.basename(exporter.filename_hint)
        basename = os.path.splitext(basename)[0]
        basename = re.sub(r'[^\w-]+', '_', basename)
        self._basename = re.sub(r'_*[rv]\d+', '', basename)
        
        self._setup_ui()
        
        # First screenshot.
        self.take_full_screenshot()
    
    def _setup_ui(self):
        
        self.setLayout(QtGui.QVBoxLayout())
        
        self._task_combo = ComboBox()
        self._task_combo.addItem('Loading...', {'loading': True})
        self._task_combo.currentIndexChanged.connect(self._task_changed)
        
        self._name_combo = ComboBox()
        self._name_combo.addItem('Loading...', {'loading': True})
        self._name_combo.addItem('Create new stream...', {'new': True})
        self._name_combo.currentIndexChanged.connect(self._name_changed)
        
        self._tasksLabel = QtGui.QLabel("Task")
        self.layout().addLayout(hbox(
            vbox(self._tasksLabel, self._task_combo),
            vbox("Publish Stream", self._name_combo),
            spacing=4
        ))
        
        self._name_field = QtGui.QLineEdit(self._basename)
        self._name_field.setEnabled(False)
        self._name_field.editingFinished.connect(self._on_name_edited)
        
        self._version_spinbox = QtGui.QSpinBox()
        self._version_spinbox.setMinimum(1)
        self._version_spinbox.setMaximum(9999)
        self._version_spinbox.valueChanged.connect(self._on_version_changed)
        self._version_warning_issued = False
        
        self.layout().addLayout(hbox(
            vbox("Name", self._name_field),
            vbox("Version", self._version_spinbox),
            spacing=4
        ))
        
        # Get publish data in the background.
        self.loaded_publishes.connect(self._populate_existing_data)
        self._thread = QtCore.QThread()
        self._thread.run = self._fetch_existing_data
        self._thread.start()
        
        self._description = QtGui.QTextEdit('')
        self._description.setMaximumHeight(100)
        
        self._thumbnail_path = None
        self._thumbnail_canvas = QtGui.QLabel()
        self._thumbnail_canvas.setFrameShadow(QtGui.QFrame.Sunken)
        self._thumbnail_canvas.setFrameShape(QtGui.QFrame.Panel)
        self._thumbnail_canvas.setToolTip("Click to specify part of screen.")
        self._thumbnail_canvas.mouseReleaseEvent = self.take_partial_screenshot
        
        self.layout().addLayout(hbox(
            vbox("Describe Your Changes", self._description),
            vbox("Thumbnail", self._thumbnail_canvas),
        ))
        
        self._movie_path = QtGui.QLineEdit()
        self._movie_browse = QtGui.QPushButton(icon('silk/folder', size=12, as_icon=True), "Browse")
        self._movie_browse.clicked.connect(self._on_movie_browse)
        self._movie_layout = hbox(self._movie_path, self._movie_browse)
        self.layout().addLayout(vbox("Path to Movie or Frames (to be copied to publish)", self._movie_layout, spacing=4))
        self._movie_browse.setFixedHeight(self._movie_path.sizeHint().height())
        self._movie_browse.setFixedWidth(self._movie_browse.sizeHint().width() + 2)
        
        # Feature flag if you don't want to allow movie publishing.
        if not siteconfig.get_bool('FEATURE_SGPUBLISH_MOVIES', True):
            self._movie_path.setEnabled(False)
            self._movie_browse.setEnabled(False)

        self._promote_checkbox = QtGui.QCheckBox("Promote to 'Version' for review")
        # self.layout().addWidget(self._promote_checkbox)
        
        self._timelog_spinbox = TimeSpinner()
        add_hour = QtGui.QPushButton("+1 Hour")
        add_hour.setFixedHeight(self._timelog_spinbox.sizeHint().height())
        @add_hour.clicked.connect
        def on_add_hour():
            self._timelog_spinbox.setValue(self._timelog_spinbox.value() + 60)
        add_day = QtGui.QPushButton("+1 Day")
        add_day.setFixedHeight(self._timelog_spinbox.sizeHint().height())
        @add_day.clicked.connect
        def on_add_day():
            self._timelog_spinbox.setValue(self._timelog_spinbox.value() + 60 * 8)
        
        self.layout().addLayout(hbox(
            vbox("Time to Log", hbox(self._timelog_spinbox, "hrs:mins", add_hour, add_day)),
            vbox("Review", self._promote_checkbox),
        ))
        
    def _fetch_existing_data(self):
        try:
            sgfs = SGFS()
            tasks = sgfs.entities_from_path(self._exporter.workspace)
            if not tasks:
                raise ValueError('No entities in workspace %r' % self._exporter.workspace)
            if any(x['type'] != 'Task' for x in tasks):
                raise ValueError('Non-Task entity in workspace %r' % self._exporter.workspace)
            publishes = sgfs.session.find(
                'PublishEvent',
                [
                    ('sg_link.Task.id', 'in') + tuple(x['id'] for x in tasks),
                    ('sg_type', 'is', self._exporter.publish_type),
                    ('sg_version', 'greater_than', 0), # Skipped failures.
                ], [
                    'code',
                    'sg_version'
                ]
            )

        except Exception as e:
            self._task_combo.clear()
            self._task_combo.addItem('Loading Error! %s' % e, {})
            raise
        
        else:
            self.loaded_publishes.emit(tasks, publishes)
        
    def _populate_existing_data(self, tasks, publishes):
        
        if tasks:
            entity = tasks[0].fetch('entity')
            name = entity.get('code') or entity.get('name')
            if name:
                self._tasksLabel.setText('Task on %s %s' % (entity['type'], name))

        history = self._exporter.get_previous_publish_ids()
        
        select = None

        publishes.sort(key=lambda p: p['sg_version'])
        
        for t_i, task in enumerate(tasks):
            name_to_publish = {}
            for publish in publishes:
                if publish['sg_link'] is not task:
                    continue

                self._existing_streams.add((task['id'], publish['code']))

                name = publish['code']
                name_to_publish[name] = publish
                
                if publish['id'] in history:
                    select = t_i, name

            self._task_combo.addItem('%s - %s' % task.fetch(('step.Step.short_name', 'content')), {
                'task': task,
                'publishes': name_to_publish,
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
        was_new = 'new' in data or 'loading' in data
        self._name_combo.clear()
        data = self._task_combo.currentData() or {}
        
        for name, publish in sorted(data.get('publishes', {}).iteritems()):
            self._name_combo.addItem('%s (v%04d)' % (name, publish['sg_version']), {'name': name, 'publish': publish})
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
        self._version_spinbox.setValue(data.get('publish', {}).get('sg_version', 0) + 1)
    
    def _on_name_edited(self):
        name = str(self._name_field.text())
        name = re.sub(r'\W+', '_', name).strip('_')
        self._name_field.setText(name)
    
    def _on_version_changed(self, new_value):
        data = self._name_combo.itemData(self._name_combo.currentIndex())
        if data.get('publish') and new_value != data['publish']['sg_version'] + 1 and not self._version_warning_issued:
            res = QtGui.QMessageBox.warning(None,
                "Manual Versions?",
                "Are you sure you want to change the version?\n"
                "The next one has already been selected for you...",
                QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel,
                QtGui.QMessageBox.Cancel
            )
            if res & QtGui.QMessageBox.Cancel:
                self._version_spinbox.setValue(data['publish']['sg_version'] + 1)
                return
            self._version_warning_issued = True
    
    def _on_movie_browse(self):
        
        existing = str(self._movie_path.text())
        
        dialog = QtGui.QFileDialog(None, "Select Movie or First Frame")
        dialog.setFilter('Movie or Frame (*.mov *.exr *.tif *.tiff *.jpg *.jpeg)')
        dialog.setFileMode(dialog.ExistingFile)
        dialog.setDirectory(os.path.dirname(existing) if existing else os.getcwd())
        if existing:
            dialog.selectFile(existing)
        
        if not dialog.exec_():
            return
        
        files = dialog.selectedFiles()
        path = str(files.First())
        self.setFrames(path)

    def setFrames(self, path):
        self._movie_path.setText(path)
        if path:
            self._promote_checkbox.setCheckState(Qt.Checked)
        
    def take_full_screenshot(self):
        pass
    
    def take_partial_screenshot(self, *args):
        path = tempfile.NamedTemporaryFile(suffix=".png", prefix="screenshot", delete=False).name

        self.beforeScreenshot.emit()
        
        if sys.platform.startswith('darwin'):
            # use built-in screenshot command on the mac
            proc = subprocess.Popen(['screencapture', '-mis', path])
        else:
            proc = subprocess.Popen(['import', path])
        proc.wait()
        
        self.afterScreenshot.emit()
        
        if os.stat(path).st_size:
            self.setThumbnail(path)
    
    def setThumbnail(self, path):
        self._thumbnail_path = path
        pixmap = QtGui.QPixmap(path).scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._thumbnail_canvas.setPixmap(pixmap)
        self._thumbnail_canvas.setFixedSize(pixmap.size())
    
    def name(self):
        data = self._name_combo.currentData()
        return data.get('name', str(self._name_field.text()))
        
    def description(self):
        return str(self._description.toPlainText())
    
    def version(self):
        return self._version_spinbox.value()
    
    def thumbnail_path(self):
        return self._thumbnail_path
    
    def _path_is_image(self, path):
        if os.path.splitext(path)[1][1:].lower() in (
            'jpg', 'jpeg', 'tif', 'tiff', 'exr',
        ):
            return path
    
    def frames_path(self):
        path = str(self._movie_path.text())
        if path and self._path_is_image(path):
            return path
        return None
    
    def movie_path(self):
        path = str(self._movie_path.text())
        if path and not self._path_is_image(path):
            return path
        return None
    
    def safety_check(self, **kwargs):
        
        # Check that the name is unique for publishes on this task.
        task = self._task_combo.currentData().get('task')
        existing_name = self._name_combo.currentData().get('name')
        new_name = str(self._name_field.text())
        if existing_name is None and (task['id'], new_name) in self._existing_streams:
            print 'XXX', task['id'], repr(existing_name), repr(new_name)
            print self._existing_streams
            QtGui.QMessageBox.critical(self,
                "Name Collision",
                "You cannot create a new stream with the same name as an"
                " existing one. Please select the existing stream or enter a"
                " unique name.",
            )
            # Fatal.
            return False
        
        # Promoting to version without a movie.
        if self._promote_checkbox.isChecked() and not (self.frames_path() or self.movie_path()):
            QtGui.QMessageBox.critical(self,
                "Review Version Without Movie",
                "You cannot promote a publish for review without frames or a"
                " movie.",
            )
            # Fatal.
            return False
        
        # Promoting to version without a timelog.
        if self._promote_checkbox.isChecked() and not self._timelog_spinbox.value():
            res = QtGui.QMessageBox.warning(self,
                "Version without Time Log",
                "Are you sure that this version did not take you any time?",
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                QtGui.QMessageBox.No,
            )
            if res & QtGui.QMessageBox.No:
                return False
        
        return True
        
    def export(self, **kwargs):
        with ticket_ui_context(pass_through=PublishSafetyError):
            return self._export(kwargs)
    
    def _export(self, kwargs):
    
        if not self.safety_check(**kwargs):
            raise PublishSafetyError()
        
        task_data = self._task_combo.currentData()
        task = task_data.get('task')

        if not task:
            sgfs = SGFS()
            tasks = sgfs.entities_from_path(self._exporter.workspace, 'Task')
            if not tasks:
                raise ValueError('Could not find SGFS tagged entities')
            task = tasks[0]
        
        stream_data = self._name_combo.currentData()
        parent = stream_data.get('publish')
        
        # Do the promotion.
        if self._promote_checkbox.isChecked():
            review_version_fields = self._exporter.fields_for_review_version(**kwargs)
        else:
            review_version_fields = None

        publisher = self._exporter.publish(task,
            name=self.name(),
            description=self.description(),
            version=self.version(),
            parent=parent,
            thumbnail_path=self.thumbnail_path(),
            frames_path=self.frames_path(),
            movie_path=self.movie_path(),
            review_version_fields=review_version_fields,
            export_kwargs=kwargs,
        )
        
        # Create the timelog.
        minutes = self._timelog_spinbox.value()
        if minutes:
            publisher.sgfs.session.create('TimeLog', {
                'project': publisher.entity.project(),
                'entity': publisher.link,
                'user': publisher.sgfs.session.guess_user(),
                'duration': minutes,
                'description': '%s_v%04d' % (publisher.name, publisher.version),
                'date': datetime.datetime.utcnow().date(),
            })
        
        return publisher

