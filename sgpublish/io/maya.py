from __future__ import absolute_import

import os

from . import base

from maya import cmds

__also_reload__ = ['.base']


class Exporter(base.Exporter):
    
    def __init__(self, *args, **kwargs):
        super(Exporter, self).__init__(*args, **kwargs)
    
    @property
    def filename_hint(self):
        return self._filename_hint or cmds.file(q=True, sceneName=True) or None
    
    @property
    def workspace(self):
        return self._workspace or cmds.workspace(query=True, rootDirectory=True) or os.getcwd()
    
    def get_previous_publish_ids(self):
        ids = cmds.fileInfo('sgpublish_%s_ids' % self.publish_type, query=True)
        return set(int(x.strip()) for x in ids[0].split(',')) if ids else set()
    
    def record_publish_id(self, id_):
        ids = self.get_previous_publish_ids()
        ids.add(id_)
        cmds.fileInfo('sgpublish_%s_ids' % self.publish_type, ','.join(str(x) for x in sorted(ids)))
