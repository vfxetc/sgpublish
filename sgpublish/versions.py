from sgfs import SGFS


def promote_publish(publish, **kwargs):
    
    publish.fetch((
        'code',
        'sg_version',
        'created_by',
        'description',
        'sg_link',
        'sg_link.Task.entity',
        'sg_path_to_frames',
        'sg_path_to_movie',
        'sg_qt',
        'project',
    ))
    
    fields = {
        'code': '%s_v%04d' % (publish['code'], publish['sg_version']),
        'created_by': publish['created_by'],
        'description': publish['description'],
        'entity': publish['sg_link']['entity'],
        'project': publish['project'],
        'sg_path_to_frames': publish['sg_path_to_frames'],
        'sg_path_to_movie': publish['sg_path_to_movie'],
        'sg_publish': publish,
        'sg_qt': publish['sg_qt'],
        'sg_task': publish['sg_link'],
        'user': publish['created_by'], # Artist.
        
        # Just because the old "Submit Version" tool had these.
        'sg_frames_aspect_ratio': 1.0,
        'sg_movie_aspect_ratio': 1.0,
        'sg_department': publish['sg_link']['step'].fetch('code') or 'Daily',
    }

    # Look up Maya frame information from the tag.
    sgfs = SGFS(session=publish.session)
    tags = sgfs.get_directory_entity_tags(sgfs.path_for_entity(publish))
    if tags and 'maya' in tags[0]:
        min_time = tags[0]['maya']['min_time']
        max_time = tags[0]['maya']['max_time']
        fields.update({
            'sg_first_frame': int(min_time),
            'sg_last_frame': int(max_time),
            'frame_count': int(max_time - min_time + 1),
        })
    
    fields.update(kwargs)
    
    # Create the new version.
    version = sgfs.session.create('Version', fields)
    
    # Share thumbnails.
    sgfs.session.share_thumbnail(entities=[version.minimal], source_entity=publish.minimal)
    
    # Set the status on the task.
    sgfs.session.update('Task', publish['sg_link']['id'], {
        'sg_status_list':'rev',
    })
    
    return version
