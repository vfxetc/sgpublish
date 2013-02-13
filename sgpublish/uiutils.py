import functools
import os
import subprocess
import sys

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt


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


def call_open(x):
    if sys.platform.startswith('darwin'):
        subprocess.call(['open', x])
    else:
        subprocess.call(['xdg-open', x])


def announce_publish_success(
    publisher,
    title="Published \"{publisher.type}\"",
    message="Version {publisher.version} of \"{publisher.name}\" has been published.",
    open_folder=True,
    open_shotgun=True,
):

    msg = QtGui.QMessageBox()
    msg.setWindowTitle(title.format(publisher=publisher))
    msg.setText(message.format(publisher=publisher))
    
    if open_folder:
        folder_button = msg.addButton("Open Folder", QtGui.QMessageBox.AcceptRole)
        folder_button.clicked.connect(functools.partial(call_open, publisher.directory))
    
    if open_shotgun:
        shotgun_button = msg.addButton("Open Shotgun", QtGui.QMessageBox.AcceptRole)
        shotgun_button.clicked.connect(functools.partial(call_open, publisher.entity.url))
        
    msg.addButton("Close", QtGui.QMessageBox.RejectRole)
    
    msg.exec_()


_icons_by_name = {}
def icon(name, size=None, as_icon=False):
    
    try:
        icon = _icons_by_name[name]
    except KeyError:
    
        path = os.path.abspath(os.path.join(__file__, 
            '..', '..',
            'art', 'icons', name + (os.path.splitext(name)[1] or '.png')
        ))

        if os.path.exists(path):
            icon = QtGui.QPixmap(path)
        else:
            icon = None
    
        _icons_by_name[name] = icon
    
    if icon and size:
        icon = icon.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    
    if icon and as_icon:
        icon = QtGui.QIcon(icon)
    
    return icon

