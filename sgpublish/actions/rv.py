import os
import re
import subprocess
import sys

from sgactions.utils import notify, alert
from sgfs import SGFS


PLAYABLE_EXTS = set(('.dpx', '.mov', '.jpg', '.jpeg', '.exr', '.mp4', '.aif'))


def bake_url(args):
    return 'rvlink://baked/%s' % ((' ' + ' '.join(args)).encode('hex'))

def rvlink(cmd):
    url = bake_url(cmd)
    if sys.platform == 'darwin':
        subprocess.check_call(['open', url])
    else:
        subprocess.check_call(['xdg-open', url])


def run_play(entity_type, selected_ids, **kwargs):

    sgfs = SGFS()
    entities = sgfs.session.get(entity_type, selected_ids)

    if entity_type == 'PublishEvent':
        sgfs.session.fetch(entities, ('code', 'sg_type', 'path_to_frames', 'path_to_movie', 'path', 'link.Task.entity'))
    elif entity_type == 'Version':
        sgfs.session.fetch(entities, ('code', 'path_to_frames', 'path_to_movie', 'entity'))
    else:
        alert('Cannot play %s entities in RV.' % entity_type)
        return

    chunks = []

    for entity in entities:

        skipped_exts = []

        for path_key in ('path_to_frames', 'path_to_movie', 'path'):

            path = (entity.get(path_key) or '').strip()
            if not path:
                continue

            ext = os.path.splitext(path)[1]
            if ext not in PLAYABLE_EXTS:
                skipped_exts.append(ext)
                continue

            notify('Opening %s in RV...' % path)

            # Convert any %04d into ####
            rv_path = re.sub(r'(?:%0?(\d)[sd])', lambda m: '#' * int(m.group(1)), path)

            # Go looking for audio.
            if entity_type == 'PublishEvent':
                shot = entity['link.Task.entity']
            else:
                shot = entity['entity']
            if shot:
                audio = sgfs.session.find_one('PublishEvent', [
                    ('sg_type', 'is', 'audio'),
                    ('link.Task.entity', 'is', shot),
                ], ['path'])
            else:
                audio = None

            # Open it (optionally with audio).
            if audio:
                chunks.extend(('[', rv_path, audio['path'], ']'))
            else:
                chunks.append(rv_path)
            break

        else:
            if skipped_exts:
                alert("""We don't know how to play %s %d ("%s") with %s extensions.""" % (
                    entity['sg_type'] + ' Publish' if entity_type == 'PublishEvent' else entity_type,
                    entity['id'],
                    entity['code'],
                    '/'.join(sorted(skipped_exts))
                ))
            else:
                alert("""%s %d ("%s") has nothing to play.""" % (
                    entity['sg_type'].title() + ' Publish' if entity_type == 'PublishEvent' else entity_type,
                    entity['id'],
                    entity['code'],
                ))
            return


    if chunks:
        # -l -> use lookahead cache
        # -play -> play immediately
        rvlink(['-l', '-play'] + chunks)
    else:
        alert("We don't know how to play %s entities." % entity_type)
