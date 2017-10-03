from concurrent.futures import ThreadPoolExecutor
import warnings

from metatools.deprecate import FunctionRenamedWarning
from sgfs import SGFS



GENERIC_FIELDS = (
    'sg_link',
    'sg_link.Task.entity',
    'project',
    'created_by',
)

SPECIFIC_FIELDS = (
    'code',
    'sg_version',
    'description',
    'sg_path_to_frames',
    'sg_path_to_movie',
    'sg_qt',
)


def generic_version_from_publish(publish, sgfs=None):
    """Get the generic fields for a Version that is derived from a Publish.

    Only the fields that would be shared by multiple Versions derived from
    the same Publish.

    """

    publish.fetch(GENERIC_FIELDS)

    fields = {
        'entity': publish['sg_link']['entity'],
        'project': publish['project'],
        'sg_publish': publish,
        'sg_task': publish['sg_link'],
        'user': publish['created_by'], # Artist.
    }

    # Look up Maya frame information from the tag.
    sgfs = sgfs or SGFS(session=publish.session)
    publish_path = sgfs.path_for_entity(publish)

    tags = sgfs.get_directory_entity_tags(publish_path)
    if tags and 'maya' in tags[0]:
        min_time = tags[0]['maya']['min_time']
        max_time = tags[0]['maya']['max_time']
        fields.update({
            'sg_first_frame': int(min_time),
            'sg_last_frame': int(max_time),
            'frame_count': int(max_time - min_time + 1),
        })

    return fields


def specific_version_from_publish(publish):
    """Get the specific fields for a Version that is supposed to represent a Publish.

    Useful for when you want a Version that is effectively a copy of a Publish.
    (E.g. the original intension behind "Promote for Review".)

    """

    return {

        'code': '%s_v%04d' % (publish['code'], publish['sg_version']),
        'description': publish['description'],
        'sg_path_to_frames': publish['sg_path_to_frames'],
        'sg_path_to_movie': publish['sg_path_to_movie'],
        'sg_qt': publish['sg_qt'],
        
        # Just because the old "Submit Version" tool had these.
        # TODO: Remove in Western Post purge.
        'sg_frames_aspect_ratio': 1.0,
        'sg_movie_aspect_ratio': 1.0,

        # I should be able to do this as a very deep fetch.
        # TODO: Remove in Western Post purge.
        'sg_department': publish['sg_link']['step'].fetch('code') or 'Daily',
    }


def create_versions_for_publish(publish, version_fields, sgfs=None):

    sgfs = sgfs or SGFS(session=publish.session)
    generic_data = generic_version_from_publish(publish, sgfs=sgfs)

    versions = []

    # N.B. This used to be 4 threads, but it was causing collisions in
    # Shotgun's servers.
    with ThreadPoolExecutor(1) as executor:

        creation_futures = []
        for fields in version_fields:

            for key, value in generic_data.iteritems():
                fields.setdefault(key, value)

            # Create/update the Version entity.
            # We allow the user to pass through their own entity for rare cases
            # when they need to modify existing ones.
            version_entity = fields.pop('__version_entity__', None)
            if version_entity is not None:
                future = executor.submit(sgfs.session.update, 'Version', version_entity['id'], fields)
                creation_futures.append((fields, version_entity, future))
            else:
                # Can't put this in the generic fields cause we are only
                # allowed to do it when creating an entity.
                fields['created_by'] = publish['created_by']
                future = executor.submit(sgfs.session.create, 'Version', fields)
                creation_futures.append((fields, None, future))

        final_futures = []
        for fields, version_entity, future in creation_futures:
            version_entity = version_entity or future.result()
            versions.append(version_entity)

            # Share thumbnails if the user didn't provide them.
            if not fields.get('image'):
                final_futures.append(executor.submit(sgfs.session.share_thumbnail,
                    entities=[version_entity.minimal],
                    source_entity=publish.minimal,
                ))

            # Set the status/version on the task.
            # TODO: Make this optional when we revise the review process.
            final_futures.append(executor.submit(sgfs.session.update,
                'Task',
                publish['sg_link']['id'],
                {
                    'sg_status_list': 'rev',
                    'sg_latest_version': version_entity,
                },
            ))
            
            # Set the latest version on the entity.
            # TODO: Make this optional when we revise the review process.
            entity = publish['sg_link'].fetch('entity')
            if entity['type'] in ('Asset', 'Shot'):
                final_futures.append(executor.submit(sgfs.session.update,
                    entity['type'],
                    entity['id'],
                    {'sg_latest_version': version_entity},
                ))

            # Allow them to raise if they must.
            for future in final_futures:
                future.result()

    return versions


def create_version_from_publish(publish, fields, sgfs=None):
    """Promote Publish into a single Version which generally mimicks that Publish.

    .. seealso:: :func:`create_versions`"""

    publish.fetch(GENERIC_FIELDS + SPECIFIC_FIELDS)

    specific_data = specific_version_from_publish(publish)
    for key, value in specific_data.iteritems():
        fields.setdefault(key, value)

    return create_versions_for_publish(publish, [fields], sgfs=sgfs)[0]


def promote_publish(publish, **fields):
    """Promote Publish into a single Version which generally mimicks that Publish.

    .. warning:: Deprecated. Use :func:`create_version_from_publish` instead.

    """

    # We renamed the function when we started generalizing to having one *or more*
    # versions promoted from a publish.
    warnings.warn('promote_publish was refactored into sgpublish.versions.create_version_from_publish',
        FunctionRenamedWarning, stacklevel=2)

    if 'version_entity' in fields:
        fields['__version_entity__'] = fields.pop('version_entity')

    return create_version_from_publish(publish, fields)



