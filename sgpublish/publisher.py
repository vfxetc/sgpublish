import os
from subprocess import check_call
import datetime
import itertools

import concurrent.futures

from sgfs import SGFS
from sgsession import Session, Entity

from . import utils

__also_reload__ = [
    '.utils',
    'sgfs.template',
    'sgfs',
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
    
    def __init__(self, link, type, name, version=None, directory=None, sgfs=None, **kwargs):
        
        self.sgfs = sgfs or (SGFS(session=link.session) if isinstance(link, Entity) else SGFS())

        self._type = str(type)
        self._link = self.sgfs.session.merge(link)
        self._name = str(name)
        
        # Set attributes from kwargs.
        for name in (
            'created_by',
            'description',
            'frames_path',
            'movie_path',
            'movie_url',
            'path',
            'thumbnail_path',
        ):
            setattr(self, name, kwargs.pop(name, None))
        
        if kwargs:
            raise TypeError('too many kwargs: %r' % sorted(kwargs))
        
        # Get everything into the right type before sending it to Shotgun.
        self._normalize_attributes()
        
        # First stage of the publish: create an "empty" PublishEvent.
        self.entity = self.sgfs.session.create('PublishEvent', {
            'code': self.name,
            'created_by': self.created_by,
            'description': self.description,
            'project': self.link.project(),
            'sg_link': link,
            'sg_path_to_frames': self.frames_path,
            'sg_path_to_movie': self.movie_path,
            'sg_qt': self.movie_url,
            'sg_type': self.type,
            'sg_version': 0, # Signifies that this is "empty".
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
            self._directory = os.path.abspath(directory)
        else:
            self._directory = self.sgfs.path_from_template(link, '%s_publish' % type, dict(
                publish=self, # For b/c.
                publisher=self, 
                PublishEvent=self.entity,
                self=self.entity, # To mimick Shotgun templates.
            ))
        
        # Make sure the directory exists (after this), but it is not tagged.
        if os.path.exists(os.path.join(self._directory, '.sgfs.yml')):
            raise ValueError('directory is already tagged')
        elif not os.path.exists(self._directory):
            os.makedirs(self._directory)
        
        self._committed = False
        
        # Will be set into the tag.
        self.metadata = {}
        
        # Files to copy on commit; (src_path, dst_path)
        self._files = []
    
    def _normalize_url(self, url):
        if url is None:
            return
        if isinstance(url, dict):
            return url
        if isinstance(url, basestring):
            return {'url': url}
        return {'url': str(url)}
    
    def _normalize_attributes(self):
        self.created_by = self.created_by or self.sgfs.session.guess_user()
        self.description = str(self.description or '') or None
        self.frames_path = str(self.frames_path or '') or None
        self.movie_path = str(self.movie_path or '') or None
        self.movie_url = self._normalize_url(self.movie_url) or None
        self.path = str(self.path or '') or None
        self.thumbnail_path = str(self.thumbnail_path or '') or None

    @property
    def type(self):
        return self._type
    
    @property
    def link(self):
        return self._link
    
    @property
    def name(self):
        return self._name
    
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
    
    def isabs(self, dst_name):
        """Is the given path absolute and within the publish directory?"""
        return dst_name.startswith(self._directory)
    
        
    def abspath(self, dst_name):
        """Get the abspath of the given name within the publish directory.
        
        If it is already within the directory, then makes no change to the path.
        
        """
        if self.isabs(dst_name):
            return dst_name
        else:
            return os.path.join(self._directory, dst_name.lstrip('/'))
    
    def add_file(self, src_path, dst_name=None, make_unique=False):
        """Queue a file (or folder) to be copied into the publish.
        
        :param str src_path: The path to copy into the publish.
        :param dst_name: Where to copy it to.
        :type dst_name: str or None.
        
        ``dst_name`` will default to the basename of the source path. ``dst_name``
        will be treated as relative to the :attr:`.path` if it is not contained
        withing the :attr:`.directory`.
        
        """
        dst_name = dst_name or os.path.basename(src_path)
        if make_unique:
            dst_name = self.unique_name(dst_name)
        elif self.file_exists(dst_name):
            raise ValueError('the file already exists in the publish')
        dst_path = self.abspath(dst_name)
        self._files.append((src_path, dst_path))
        return dst_path
    
    def file_exists(self, dst_name):
        """If added via :meth:`.add_file`, would it clash with an existing file?"""
        dst_path = self.abspath(dst_name)
        return os.path.exists(dst_path) or any(x[1] == dst_path for x in self._files)
    
    def unique_name(self, dst_name):
        """Append numbers to the end of the name if nessesary to make the name
        unique for :meth:`.add_file`.
        
        """
        if not self.file_exists(dst_name):
            return dst_name
        base, ext = os.path.splitext(dst_name)
        for i in itertools.counter(1):
            unique_name = '%s_%d%s' % (base, i, ext)
            if not self.file_exists(unique_name):
                return unique_name
    
    def commit(self):
        
        # As soon as one publish attempt is made, we force a full retry.
        if self._committed:
            raise ValueError('publish already comitted')
        self._committed = True
        
        # Cleanup all user-settable attributes that are sent to Shotgun.
        self._normalize_attributes()
        
        try:
            
            updates = {
                'description': self.description,
                'sg_path': self.path,
                'sg_path_to_frames': self.frames_path,
                'sg_path_to_movie': self.movie_path,
                'sg_qt': self.movie_url,
                'sg_version': self._version,
            }
            
            # Force the updated into the entity for the tag, since the Shotgun
            # update may not complete by the time that we tag the directory.
            self.entity.update(updates)
            
            executor = concurrent.futures.ThreadPoolExecutor(4)
            
            # Start the second stage of the publish.
            update_future = executor.submit(self.sgfs.session.update,
                'PublishEvent',
                self.entity['id'],
                updates,
            )
                
            if self.thumbnail_path:
                
                # Start the thumbnail upload in the background.
                thumbnail_future = executor.submit(self.sgfs.session.upload_thumbnail,
                    self.entity['type'],
                    self.entity['id'],
                    self.thumbnail_path,
                )
                
                # Schedule it for copy.
                thumbnail_name = 'thumbnail' + os.path.splitext(self.thumbnail_path)[1]
                thumbnail_name = self.add_file(
                    self.thumbnail_path,
                    thumbnail_name,
                    make_unique=True
                )
            
            else:
                thumbnail_future = None
            
            # Copy in the scheduled files.
            for src_path, dst_path in self._files:
                dst_dir = os.path.dirname(dst_path)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)
                check_call(['cp', '-rp', src_path, dst_path])
            
            # Tag the directory.
            our_metadata = {}
            if self._parent:
                our_metadata['parent'] = self._parent.minimal
            if self.thumbnail_path:
                our_metadata['thumbnail'] = thumbnail_name.encode('utf8') if isinstance(thumbnail_name, unicode) else thumbnail_name
            full_metadata = dict(self.metadata)
            full_metadata['sgpublish'] = our_metadata
            self.sgfs.tag_directory_with_entity(self._directory, self.entity, full_metadata)
            
            # Set permissions. I would like to own it by root, but we need root
            # to do that. We also leave the directory writable, but sticky.
            check_call(['chmod', '-R', 'a=rX', self._directory])
            check_call(['chmod', 'a+t,u+w', self._directory])
            
            # Wait for the Shotgun updates.
            update_future.result()
            if thumbnail_future:
                thumbnail_future.result()
        
        # Delete the publish on any error.
        except:
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
    
    def promote_to_version(self, **kwargs):
        
        
        fields = {
            'code': '%s_v%04d' % (self.name, self.version),
            'created_by': self.created_by,
            'description': self.description or '',
            'entity': self.link.parent(),
            'project': self.link.project(),
            'sg_path_to_frames': self.frames_path,
            'sg_path_to_movie': self.movie_path,
            'sg_qt': self.movie_url,
            'user': self.created_by, # "Artist"
        }
        
        fields.update(kwargs)
        
        return self.sgfs.session.create('Version', fields)


        