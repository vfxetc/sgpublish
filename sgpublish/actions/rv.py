import os
import subprocess
import sys
import urllib

from sgactions.utils import notify, alert
from sgfs import SGFS

def rvlink(cmd):
    url = 'rvlink://%s' % urllib.quote(' '.join("'%s'" % x for x in cmd))
    if sys.platform == 'darwin':
        subprocess.check_call(['open', url])
    else:
        sunprocess.check_call(['xdg-open', url])

def run_play(entity_type, selected_ids, **kwargs):

    sgfs = SGFS()
    entities = sgfs.session.merge([{'type': entity_type, 'id': id_} for id_ in selected_ids])

    if entity_type == 'PublishEvent':
        sgfs.session.fetch(entities, ('sg_type', 'qt', 'path_to_frames', 'path_to_movie', 'path'))

        for entity in entities:

            path = (
                (entity['path_to_frames'] or '').strip() or
                (entity['path_to_movie'] or '').strip() or
                (entity['path'] or '').strip()
            )
            if not path:
                alert("PublishEvent %d has nothing to play." % entity['id'])
                return

            ext = os.path.splitext(path)[1]
            if ext in ('.dpx', '.mov', '.jpg'):
                notify('Playing %s in RV...' % path)
                rvlink(['-l', '-play', path])

            else:
                alert("We don't know how to play \"%s\" %s publishes." % (ext, entity['sg_type']))
                return


    else:
        alert("We don't know how to play %s entities." % entity_type)
