import os

from ..publisher import Publisher

__also_reload__ = ['..publisher']


class Exporter(object):
    
    def __init__(self, workspace=None, filename_hint=None, publish_type=None):
        self._workspace = workspace
        self._filename_hint = filename_hint
        self._publish_type = publish_type

    @property
    def publish_type(self):
        return self._publish_type
    
    @property
    def filename_hint(self):
        return self._filename_hint
    
    @property
    def workspace(self):
        return self._workspace or os.getcwd()
    
    def get_previous_publish_ids(self):
        return set()
    
    def record_publish_id(self, id_):
        pass
    
    def publish(self, task, name, description, version=None, thumbnail=None, **kwargs):
        
        publish_type = self.publish_type
        if not publish_type:
            raise ValueError('cannot publish without type')
        
        with Publisher(
            type=publish_type,
            link=task,
            name=name,
            description=description,
            version=version,
        ) as publisher:
            
            # Record the ID before the export so that it is included.
            self.record_publish_id(publisher.id)
            
            # Set the thumbnail before so that the export may override it.
            publisher.thumbnail_path = thumbnail
            
            self.export_publish(publisher, **kwargs)
            return publisher
    
    def export_publish(self, publisher, **kwargs):
        self.export(publisher.directory, None, **kwargs)
    
    def export(self, directory, path, **kwargs):
        raise NotImplementedError()


class Importer(object):
    
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
        
    def import_publish(self, publish):
        # This gets the entity, not a Publisher.
        # Call `self.import(publish['sg_path'])`.
        pass
    
    def import_(self, path):
        raise NotImplementedError()