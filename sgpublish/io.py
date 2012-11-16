
class Exporter(object):
    
    @property
    def basename(self):
        return None
    
    def export_publish(self, publisher):
        self.export(publisher.directory, None)
    
    def export(self, directory, path):
        # The path *may* be None.
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