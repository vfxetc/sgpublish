import os
import subprocess

from sgfs import SGFS
from sgactions.utils import notify

from sgpublish import versions


def run(entity_type, selected_ids, **kwargs):
    sgfs = SGFS()
    
    for id_ in selected_ids:
        
        entity = sgfs.session.merge({'type': entity_type, 'id': id_})
        task, code, version, frames_path, movie_path = entity.fetch(('sg_link', 'code', 'sg_version', 'sg_path_to_frames', 'sg_path_to_movie'))
        
        # Can't promote it without a movie.
        if not (frames_path or movie_path):
            notify('Version "%s_v%04d" does not have frames or a movie' % (code, version), sticky=True)
            continue
        
        # Make sure it doesn't already exist.
        existing = sgfs.session.find('Version', [
            ('sg_task', 'is', task),
            ('code', 'is', '%s_v%04d' % (code, version)),
        ])
        if existing:
            notify('Version "%s_v%04d" already exists' % (code, version), sticky=True)
            continue
        
        versions.promote_publish(entity)
        notify('Promoted to version "%s_v%04d"' % (entity['code'], entity['sg_version']))    
