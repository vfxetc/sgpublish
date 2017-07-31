from __future__ import absolute_import

import os

from . import base

import nuke


class Exporter(base.Exporter):
    
    def __init__(self, *args, **kwargs):
        super(Exporter, self).__init__(*args, **kwargs)
    
    @property
    def filename_hint(self):
        return self._filename_hint or nuke.scriptName()
    
    @property
    def workspace(self):
        return self._workspace or os.path.dirname(nuke.scriptName())
