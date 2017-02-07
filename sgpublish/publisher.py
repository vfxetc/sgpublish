from subprocess import check_call
import datetime
import itertools
import json
import logging
import os
import shutil
import re

import concurrent.futures

from sgfs import SGFS
from sgsession import Session, Entity
from shotgun_api3.shotgun import Fault as ShotgunFault

from . import utils
from . import versions


log = logging.getLogger(__name__)


_kwarg_to_field = {
    'created_by': 'created_by',
    'description': 'description',
    'frames_path': 'sg_path_to_frames',
    'movie_path': 'sg_path_to_movie',
    # 'movie_url': 'sg_qt', # leaving this one out until we figure out URLs better.
    'source_publish': 'sg_source_publish',
    'source_publishes': 'sg_source_publishes', # deprecated
    'trigger_event': 'sg_trigger_event_id',
}


class Publisher(object):

    """A publishing assistant.

    This object encapsulates the logic for the required two-stage creation cycle
    of a Shotgun ``PublishEvent``.

    This object is used as a context manager such that it will cleanup
    the first stage of the commit if there is an exception::

        >>> with sgpublish.Publisher(link=task, type="maya_scene", code=name,
        ...         ) as publisher:
        ...     publisher.add_file(scene_file)

    The names of the parameters and attributes are largely the same as that of
    the underlying ``PublishEvent`` itself, albeit with the ``"sg_"`` prefix
    removed.

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

    def __init__(self, link=None, type=None, name=None, version=None, parent=None,
        directory=None, sgfs=None, template=None, **kwargs
    ):

        if not sgfs:
            if isinstance(template, Entity):
                sgfs = SGFS(session=template.session)
            elif isinstance(link, Entity):
                sgfs = SGFS(session=link.session)
            else:
                sgfs = SGFS()
        self.sgfs = sgfs

        if template:

            template = sgfs.session.merge(template)
            to_fetch = ['sg_link', 'sg_type', 'code', 'sg_version']
            to_fetch.extend(_kwarg_to_field.itervalues())
            template.fetch(to_fetch)

            tpl_link, tpl_type, tpl_name, tpl_version = template.get(('sg_link', 'sg_type', 'code', 'sg_version'))
            link = link or tpl_link
            type = type or tpl_type
            name = name or tpl_name
            version = version or tpl_version

            kwargs.setdefault('source_publish', template)
            kwargs.setdefault('source_publishes', [template])
            for key, field in _kwarg_to_field.iteritems():
                kwargs.setdefault(key, template.get(field))

            if not kwargs.get('thumbnail_path'):
                # We certainly jump through a lot of hoops to do this...
                # Perhaps this should be sgfs.get_entity_tags(entity)
                publish_path = sgfs.path_for_entity(template)
                if publish_path:
                    tags = sgfs.get_directory_entity_tags(publish_path)
                    tags = [tag for tag in tags if tag['entity'] == template]
                    if tags:
                        meta = tags[0].get('sgpublish', {})
                        thumbnail = meta.get('thumbnail')
                        if thumbnail:
                            kwargs['thumbnail_path'] = os.path.join(publish_path, thumbnail)

        if not (link and type and name):
            raise ValueError('requires link, type, and name')

        self._type = str(type)
        self._link = self.sgfs.session.merge(link)
        self._name = str(name)
        self._parent = parent

        if re.search(r'[^\w\.,-]', self._name):
            raise ValueError('name cannot have spaces or special characters', self._name)

        # Get information about the promotion for review.
        self._review_version_entity = None
        self._review_version_fields = kwargs.pop('review_version_fields', None)

        # To only allow us to commit once.
        self._committed = False

        # Will be set into the tag.
        self.metadata = {}

        # Files to copy on commit; (src_path, dst_path)
        self._files = []

        # Set attributes from kwargs.
        for name in (
            'created_by',
            'description',
            'frames_path',
            'movie_path',
            'movie_url',
            'path',
            'source_publish',
            'source_publishes',
            'thumbnail_path',
            'trigger_event',
            'extra_fields',
        ):
            setattr(self, name, kwargs.pop(name, None))

        if kwargs:
            raise TypeError('too many kwargs: %r' % sorted(kwargs))

        # Required for normalizing.
        self._directory = None

        # Get everything into the right type before sending it to Shotgun.
        self._normalize_attributes()

        # Prep for async processes. We can do a lot of "frivolous" Shotgun
        # queries at the same time since we must do at least one.
        executor = concurrent.futures.ThreadPoolExecutor(8)
        futures = []

        # Figure out the version number (async).
        if version is None:
            futures.append(executor.submit(self._set_automatic_version))
        else:
            self._version = int(version)

        # Grab all data on the link (assuming that is all that is used when
        # creating publish templates).
        futures.append(executor.submit(self.link.fetch_core))

        # Create the review version stub (async).
        if self._review_version_fields is not None:
            futures.append(executor.submit(self._get_review_version))

        # First stage of the publish: create an "empty" PublishEvent.
        initial_data = {
            'code': self.name,
            'created_by': self.created_by,
            'description': self.description,
            'project': self.link.project(),
            'sg_link': self.link,
            'sg_path_to_frames': self.frames_path,
            'sg_path_to_movie': self.movie_path,
            'sg_qt': self.movie_url,
            'sg_source_publish': self.source_publish or None, # singular
            'sg_source_publishes': self.source_publishes or [], # multiple
            'sg_trigger_event_id': self.trigger_event['id'] if self.trigger_event else None,
            'sg_type': self.type,
            'sg_version': 0, # Signifies that this is "empty".
        }
        initial_data.update(self.extra_fields)
        try:
            self.entity = self.sgfs.session.create('PublishEvent', initial_data)
        except ShotgunFault:
            if not self.link.exists():
                raise RuntimeError('%s %d (%r) has been retired' % (link['type'], link['id'], link.get('name')))
            else:
                raise

        # Lets have our async processes catch up.
        for future in futures:
            future.result()

        # Manually forced directory.
        if directory is not None:
            self._directory_supplied = True

            # Make it if it doesn't already exist, but don't care if it does.
            self._directory = os.path.abspath(directory)

        else:
            self._directory_supplied = False

            # Find a unique name using the template result as a base.
            base_path = self.sgfs.path_from_template(link, '%s_publish' % type, dict(
                publish=self, # For b/c.
                publisher=self,
                PublishEvent=self.entity,
                self=self.entity, # To mimick Shotgun templates.
            ))
            unique_iter = ('%s_%d' % (base_path, i) for i in itertools.count(1))
            for path in itertools.chain([base_path], unique_iter):
                try:
                    os.makedirs(path)
                except OSError as e:
                    if e.errno != 17: # File exists
                        raise
                else:
                    self._directory = path
                    break

        # Make the directory so that tools which want to manually copy files
        # don't have to.
        utils.makedirs(self._directory)

        # If the directory is tagged with existing entities, then we cannot
        # proceed. This allows one to retire a publish and then overwrite it.
        tags = self.sgfs.get_directory_entity_tags(self._directory)
        if any(tag['entity'].exists() for tag in tags):
            raise ValueError('directory is already tagged: %r' % self._directory)

    def _set_automatic_version(self):

        existing_entities = self.sgfs.session.find(
            'PublishEvent',
            [
                ('sg_link', 'is', self.link),
                ('sg_type', 'is', self.type),
                ('code', 'is', self.name),
            ],
            ['sg_version', 'created_at'],
        )

        self._version = 1
        for e in existing_entities:
            # Only increment for non-failed commits.
            if e['sg_version']:
                self._version = e['sg_version'] + 1
                self._parent = e

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
        self.movie_url = self._normalize_url(self.movie_url) or None
        self.source_publishes = self.source_publishes if self.source_publishes is not None else []

        if isinstance(self.trigger_event, int):
            self.trigger_event = {'type': 'EventLogEntry', 'id': self.trigger_event}
        else:
            self.trigger_event = self.trigger_event or None

        self.extra_fields = {} if self.extra_fields is None else self.extra_fields

        # This is uploaded, so not relative.
        self.thumbnail_path = str(self.thumbnail_path or '') or None

        # Descriptive paths are relative to the directory.
        if self._directory is not None:
            self.frames_path = os.path.join(self._directory, self.frames_path) if self.frames_path else None
            self.movie_path = os.path.join(self._directory, self.movie_path) if self.movie_path else None
            self.path = os.path.join(self._directory, self.path) if self.path else None

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
    def review_version_entity(self):
        """The stub of the review Version, or None."""
        return self._review_version_entity

    @property
    def review_version_fields(self):
        """The stub of the review fields, or None."""
        return self._review_version_fields

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

    def add_file(self, src_path, dst_name=None, make_unique=False, method='copy', immediate=False):
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

        if method not in ('copy', 'move', 'placeholder'):
            raise ValueError('bad add_file method %r' % method)

        if immediate:
            self._add_file(src_path, dst_path, method)
        else:
            self._files.append((src_path, dst_path, method))

        return dst_path

    def _add_file(self, src_path, dst_path, method):

        dst_dir = os.path.dirname(dst_path)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)

        if method == 'copy':
            shutil.copy(src_path, dst_path)
        elif method == 'move':
            shutil.move(src_path, dst_path)
        elif method == 'placeholder':
            pass # Just a placeholder.
        else:
            raise RuntimeError('bad add_file method %r' % method)

    def add_files(self, files, relative_to=None, **kwargs):

        for i, path in enumerate(files):

            if relative_to:
                # The publish will be structured relative to the given root.
                rel_path = os.path.relpath(path, relative_to)
                if utils.has_pardir(rel_path):
                    log.warning('%s is not within %s' % (path, relative_to))
                    rel_path = utils.strip_pardir(path)

                dst_path = self.add_file(path, rel_path, **kwargs)
            else:
                dst_path = self.add_file(path, **kwargs)

            # Set the publish's "path" to that of the first file.
            if not i and self.path is None:
                self.path = dst_path


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
        for i in itertools.count(1):
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
                'sg_source_publishes': self.source_publishes or [],
                'sg_trigger_event_id': self.trigger_event['id'] if self.trigger_event else None,
                'sg_version': self._version,
                'sg_metadata': json.dumps(self.metadata),
            }
            updates.update(self.extra_fields)

            # Force the updated into the entity for the tag, since the Shotgun
            # update may not complete by the time that we tag the directory
            # or promote for review.
            self.entity.update(updates)

            executor = concurrent.futures.ThreadPoolExecutor(4)
            futures = []

            # Start the second stage of the publish.
            futures.append(executor.submit(self.sgfs.session.update,
                'PublishEvent',
                self.entity['id'],
                updates,
            ))

            if self.thumbnail_path:

                # Start the thumbnail upload in the background.
                futures.append(executor.submit(self.sgfs.session.upload_thumbnail,
                    self.entity['type'],
                    self.entity['id'],
                    self.thumbnail_path,
                ))

                # Schedule it for copy.
                thumbnail_name = os.path.relpath(self.thumbnail_path, self.directory)
                if thumbnail_name.startswith('.'):
                    thumbnail_name = 'thumbnail' + os.path.splitext(self.thumbnail_path)[1]
                    thumbnail_name = self.add_file(
                        self.thumbnail_path,
                        thumbnail_name,
                        make_unique=True
                    )

            # Copy in the scheduled files.
            for file_args in self._files:
                self._add_file(*file_args)

            # Set permissions. I would like to own it by root, but we need root
            # to do that. We also leave the directory writable, but sticky.
            check_call(['chmod', '-R', 'a=rX', self._directory])
            check_call(['chmod', 'a+t,u+w', self._directory])

            # Wait for the Shotgun updates.
            for future in futures:
                future.result()

            # Tag the directory. Ideally we would like to do this before the
            # futures are waited for, but we only want to tag the directory
            # if everything was successful.
            our_metadata = {}
            if self._parent:
                our_metadata['parent'] = self.sgfs.session.merge(self._parent).minimal
            if self.thumbnail_path:
                our_metadata['thumbnail'] = thumbnail_name.encode('utf8') if isinstance(thumbnail_name, unicode) else thumbnail_name
            full_metadata = dict(self.metadata)
            full_metadata['sgpublish'] = our_metadata
            self.sgfs.tag_directory_with_entity(self._directory, self.entity, full_metadata)

            # Again, we would like to do with with the futures, but the current
            # version of this depends on the directory being tagged.
            if self._review_version_fields is not None:
                self._promote_for_review()


        except:
            self.rollback()
            raise

    def __enter__(self):
        return self

    def rollback(self):

        # Remove the entity's ID.
        id_ = self.entity.pop('id', None) or 0

        # Attempt to set the version to 0 on Shotgun.
        if id_ and self.entity.get('sg_version'):
            self.sgfs.session.update('PublishEvent', id_, {'sg_version': 0})

        # Move the folder aside.
        if not self._directory_supplied and os.path.exists(self._directory):
            failed_directory = '%s.%d.failed' % (self._directory, id_)
            check_call(['mv', self._directory, failed_directory])
            self._directory = failed_directory

    def __exit__(self, *exc_info):
        if exc_info and exc_info[0] is not None:
            self.rollback()
            return
        self.commit()

    def _get_review_version(self):
        """Get a Version entity which will reference the PublishEvent once done.

        MUST call :meth:`promote_for_review` to finalize this entity.

        """

        if self._review_version_entity is None:
            self._review_version_entity = self.sgfs.session.create('Version', {
                'code': 'stub for publishing',
                'created_by': self.created_by,
                'project': self.link.project(),
            })
        return self._review_version_entity

    def _promote_for_review(self):
        if not self._committed:
            raise RuntimeError('can only promote AFTER publishing commits')
        kwargs = dict(self._review_version_fields or {})
        if self._review_version_entity:
            kwargs.setdefault('version_entity', self._review_version_entity)
        return versions.promote_publish(self.entity, **kwargs)
