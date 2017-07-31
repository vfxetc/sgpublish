import functools
import os
import subprocess
import sys

from uitools.qt import Q, qt2py


class ComboBox(Q.QComboBox):
    
    def itemData(self, *args):
        return qt2py(super(ComboBox, self).itemData(*args))
    
    def currentData(self):
        return self.itemData(self.currentIndex())


def _box(layout, *args):
    for arg in args:
        if isinstance(arg, basestring):
            layout.addWidget(Q.QLabel(arg))
        elif isinstance(arg, Q.QLayout):
            layout.addLayout(arg)
        else:
            layout.addWidget(arg)
    return layout

hbox = lambda *args, **kwargs: _box(Q.QHBoxLayout(**kwargs), *args)
vbox = lambda *args, **kwargs: _box(Q.QVBoxLayout(**kwargs), *args)


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

    msg = Q.QMessageBox()
    msg.setWindowTitle(title.format(publisher=publisher))
    msg.setText(message.format(publisher=publisher))
    
    if open_folder:
        folder_button = msg.addButton("Open Folder", Q.QMessageBox.AcceptRole)
        folder_button.clicked.connect(functools.partial(call_open, publisher.directory))
    
    if open_shotgun:
        shotgun_button = msg.addButton("Open Shotgun", Q.QMessageBox.AcceptRole)
        shotgun_button.clicked.connect(functools.partial(call_open, publisher.entity.url))
        
    msg.addButton("Close", Q.QMessageBox.RejectRole)
    
    msg.exec_()


_icons_by_name = {}
def icon(name, size=None, as_icon=False):
    
    try:
        icon = _icons_by_name[name]
    except KeyError:
    
        path = os.path.abspath(os.path.join(__file__, 
            '..',
            'art', 'icons', name + (os.path.splitext(name)[1] or '.png')
        ))

        if os.path.exists(path):
            icon = Q.QPixmap(path)
        else:
            icon = None
    
        _icons_by_name[name] = icon
    
    if icon and size:
        icon = icon.scaled(size, size, Q.IgnoreAspectRatio, Q.SmoothTransformation)
    
    if icon and as_icon:
        icon = Q.QIcon(icon)
    
    return icon

