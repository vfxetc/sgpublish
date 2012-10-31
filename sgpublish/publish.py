import os
from subprocess import check_call

import concurrent.futures

from sgfs import SGFS


class Publish(object):
    
    def __init__(self, link, type, code, path=None, sgfs=None):
        
        self.sgfs = sgfs or SGFS(session=link.session)
        
        self.link = self.sgfs.session.merge(link)
        self.type = type
        self.code = code
        
        
        # First stage of the publish: create an "empty" PublishEvent.
        self._entity = self.sgfs.session.create('PublishEvent', {
            'sg_link': link,
            'project': self.link.project(),
            'sg_type': type,
            'code': code,
            'sg_version': 0, # Signifies that this is "empty".
        })
        
        # Determine the version number by looking at the existing publishes.
        self._version = 1
        for existing in self.sgfs.session.find('PublishEvent', [
            ('sg_link', 'is', link),
            ('sg_type', 'is', type),
            ('code', 'is', code),
            ('id', 'less_than', self._entity['id']),
        ], ['version']):
            if existing['version']:
                self._version = existing['version'] + 1
            else:
                self._version += 1
        
        # Generate the publish path.
        if path is not None:
            self._path = path
        else:
            self._path = sgfs.path_from_template(link, '%s_publish' % type,
                publish=self,
            )
        
        self._committed = False
        
        # Will be set into the tag.
        self.metadata = {}
        
        # Files to copy on commit; (src_path, dst_path)
        self._files = []
        
        # Thumbnail to publish.
        self.thumbnail_path = None
    
    @property
    def version(self):
        return self._version
    
    @property
    def path(self):
        return self._path
    
    def add_file(self, src_path, dst_name=None):
        dst_name = dst_name or os.path.basename(src_path)
        self._files.append((src_path, dst_name))
    
    def commit(self):
        
        # As soon as one publish attempt is made, we force a full retry.
        if self._committed:
            raise ValueError('publish already comitted')
        self._committed = True
        
        # We need to be able to wait for these in the except handler.
        update_future = thumbnail_future = None
        
        try:
            
            executor = concurrent.futures.ThreadPoolExecutor(4)
            
            # Start the second stage of the publish.
            update_future = executor.submit(self.sgfs.session.update,
                'PublishEvent',
                self._entity['id'],
                {
                    'sg_version': self._version,
                    'sg_path': self._path,
                },
            )
            
            # Start the thumbnail upload.
            if self.thumbnail_path:
                thumbnail_future = executor.submit(self.sgfs.session.upload_thumbnail,
                    'PublishEvent',
                    self._entity['id'],
                    self.thumbnail_path,
                )
            
            if not os.path.exists(self._path):
                os.makedirs(self._path)
            
            # Copy in the new files, and lock down the writing bit.
            for src_path, dst_name in self._files:
                dst_path = os.path.join(self._path, dst_name.lstrip('/'))
                dst_dir = os.path.dirname(dst_path)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)
                check_call(['cp', '-rp', src_path, dst_path])
                check_call(['chmod', '-R', 'a-w', dst_path])
            
            # Wait for the Shotgun update.
            update_future.result()
            
            # Tag the directory.
            self.sgfs.tag_directory_with_entity(self._path, self._entity, self.metadata)
            
            # Wait for the thumbnail.
            if thumbnail_future:
                thumbnail_future.result()
        
        # Delete the publish on any error.
        except:
            
            # Wait for other Shotgun calls first.
            try:
                update_future.result()
                if thumbnail_future:
                    thumbnail_future.result()
            except:
                pass
            
            self._delete()
            raise
        
    def __enter__(self):
        return self
    
    def _delete(self):
        id_ = self._entity.pop('id', None)
        if id_:
            self.sgfs.session.delete('PublishEvent', id_)
    
    def __exit__(self, *exc_info):
        if exc_info and exc_info[0] is not None:
            self._delete()
            return
        self.commit()
        
        