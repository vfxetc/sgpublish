import subprocess
import platform

from PyQt4 import QtCore, QtGui


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
    if platform.system() == 'Darwin':
        subprocess.call(['open', x])
    else:
        subprocess.call(['xdg-open', x])
