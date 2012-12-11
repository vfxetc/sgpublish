import os

from sgfs import SGFS


class Importer(object):
    
    def __init__(self):
        self.sgfs = SGFS()

    @property
    def workspace(self):
        return os.getcwd()

    @property
    def existing_publish(self):
    
        path = self.existing_path
        if path is None:
            return
            
        entities = self.sgfs.entities_for_path(path, 'PublishEvent')
        if len(entities) > 1:
            raise RuntimeError('multiple publishes tagged in %r' % path)
        return entities[0] if entities else None
    
    @property
    def existing_path(self):
        # For the UI to repopulate.
        return None
        
    def import_publish(self, publish, **kwargs):
        """Passthrough to the :meth:`.import_`."""
        path, directory = publish.fetch(('sg_path', 'sg_directory'))
        return self.import_(path or directory, **kwargs)
    
    def import_(self, path, **kwargs):
        raise NotImplementedError()

