import os
from subprocess import check_call
import datetime

import concurrent.futures

from sgfs import SGFS
from sgsession import Entity

from . import utils

__also_reload__ = [
    '.utils',
    'sgfs.template',
]


class Publisher(object):
    
    """Object to assist in publishing to Shotgun.
    
    This object encapsulates the logic for the required two-stage creation cycle
    of a Shotgun ``PublishEvent``.
    
    Publishes are grouped into logical streams, consisting of Shotgun
    ``PublishEvent`` entities sharing the same ``link``, ``type``, and ``code``.
    Their version numbers are automatically generated to be monotonically
    increasing within that stream.
    
    This object is generally used as a context manager such that it will cleanup
    the first stage of the commit if there is an exception::
    
        >>> with sgpublish.Publisher(link=task, type="maya_scene", code=name,
        ...         ) as publisher:
        ...     publisher.add_file(scene_file)
        
    :param link: The Shotgun entity to attach to.
    :type link: :class:`python:dict` or :class:`~sgsession.entity.Entity`
    
    :param str type: A code for the type of publish. This is significant to the
        user and publish handlers.
    
    :param str code: A name for the stream of publishes.
    
    :param path: The directory to create for the publish. If ``None``, this will
        be generated via the ``"{type}_publish"`` :class:`sgfs.Template
        <sgfs.template.Template>` found for the given ``link``.
    :type path: str or None
    
    :param str description: The publish's description; can be provided via an
        attribute before :meth:`.commit`.
    
    :param created_by: A Shotgun ``HumanUser`` for the publish to be attached to.
        ``None`` will result in a guess via :func:`.guess_shotgun_user`.
    :type created_by: :class:`~sgsession.entity.Entity`, :class:`dict`, or None
    
    :param sgfs: The SGFS to use. Will be pulled from the link's session if not
        provided.
    :type sgfs: :class:`~sgfs.sgfs.SGFS` or None
    
    """
    
    def __init__(self, link, type, name, version=None, directory=None, path=None, description=None, created_by=None, sgfs=None):
        
        self.sgfs = sgfs or (SGFS(session=link.session) if isinstance(link, Entity) else SGFS())
        
        self.link = self.sgfs.session.merge(link)
        self.type = str(type)
        self.name = str(name)
        self.description = str(description)
        self.created_by = created_by or utils.guess_shotgun_user()
        self.path = path
        
        # First stage of the publish: create an "empty" PublishEvent.
        self.entity = self.sgfs.session.create('PublishEvent', {
            'sg_link': link,
            'project': self.link.project(),
            'sg_type': self.type,
            'description': self.description,
            'code': self.name,
            'sg_version': 0, # Signifies that this is "empty".
            'created_by': self.created_by,
        })
        
        # Determine the version number by looking at the existing publishes.
        self._version = 1
        self._parent = None
        for existing in self.sgfs.session.find('PublishEvent', [
            ('sg_link', 'is', self.link),
            ('sg_type', 'is', self.type),
            ('code', 'is', self.name),
            ('id', 'less_than', self.entity['id']),
        ], ['sg_version', 'created_at']):
            if existing['sg_version']:
                self._version = existing['sg_version'] + 1
                self._parent = existing
            else:
                self._version += 1
        
        if version is not None:
            version = int(version)
            if self._parent and version <= self._parent['sg_version']:
                raise ValueError('requested version is too low')
            self._version = version
        
        # Generate the publish path.
        if directory is not None:
            self._directory = directory
        else:
            self._directory = self.sgfs.path_from_template(link, '%s_publish' % type,
                publish=self,
            )
        if not os.path.exists(self._directory):
            os.makedirs(self._directory)
        elif os.path.exists(os.path.join(self._directory, '.sgfs.yml')):
            raise ValueError('directory is already tagged')
        
        self._committed = False
        
        # Will be set into the tag.
        self.metadata = {}
        
        # Files to copy on commit; (src_path, dst_path)
        self._files = []
        
        # Thumbnail to publish.
        self.thumbnail_path = None
    
    @property
    def id(self):
        """The ID of the PublishEvent."""
        return self.entity['id']
    
    @property
    def version(self):
        """The version of the PublishEvent."""
        return self._version
    
    @property
    def directory(self):
        """The path into which all files must be placed."""
        return self._directory
    
    def add_file(self, src_path, dst_name=None):
        """Queue a file (or folder) to be copied into the publish.
        
        :param str src_path: The path to copy into the publish.
        :param dst_name: Where to copy it to.
        :type dst_name: str or None.
        
        ``dst_name`` will default to the basename of the source path. ``dst_name``
        will always be treated as relative to the :attr:`.path`, even if it
        starts with a slash.
        
        """
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
                self.entity['id'],
                {
                    'sg_version': self._version,
                    'sg_path': self.path or self._directory,
                    'description': self.description or '',
                },
            )
            
            # Start the thumbnail upload.
            if self.thumbnail_path:
                thumbnail_future = executor.submit(self.sgfs.session.upload_thumbnail,
                    'PublishEvent',
                    self.entity['id'],
                    self.thumbnail_path,
                )
                thumbnail_name = '.sgpublish.thumbnail' + os.path.splitext(self.thumbnail_path)[1]
                self.add_file(self.thumbnail_path, thumbnail_name)
            
            # Copy in the new files.
            for src_path, dst_name in self._files:
                dst_path = os.path.join(self._directory, dst_name.lstrip('/'))
                dst_dir = os.path.dirname(dst_path)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)
                check_call(['cp', '-rp', src_path, dst_path])
            
            # Tag the directory.
            our_metadata = {}
            if self._parent:
                our_metadata['parent'] = self._parent.minimal
            if self.thumbnail_path:
                our_metadata['thumbnail'] = thumbnail_name
            full_metadata = dict(self.metadata)
            full_metadata['sgpublish'] = our_metadata
            self.sgfs.tag_directory_with_entity(self._directory, self.entity, full_metadata)
            
            # Set permissions. I would like to own it by root, but we need root
            # to do that. Oh well...
            check_call(['chmod', '-R', 'a=rX', self._directory])
            
            # Wait for the Shotgun updates.
            update_future.result()
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
        id_ = self.entity.pop('id', None)
        if id_:
            self.sgfs.session.delete('PublishEvent', id_)
    
    def __exit__(self, *exc_info):
        if exc_info and exc_info[0] is not None:
            self._delete()
            return
        self.commit()
        
        