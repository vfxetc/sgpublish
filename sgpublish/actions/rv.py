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
    entities = sgfs.session.get(entity_type, selected_ids)

    if entity_type == 'PublishEvent':
        sgfs.session.fetch(entities, ('code', 'sg_type', 'path_to_frames', 'path_to_movie', 'path'))

        for entity in entities:

            skipped_exts = []

            for path_key in ('path_to_frames', 'path_to_movie', 'path'):

                path = (entity[path_key] or '').strip()
                if not path:
                    continue

                ext = os.path.splitext(path)[1]
                if ext in ('.dpx', '.mov', '.jpg'):
                    notify('Playing %s in RV...' % path)
                    rvlink(['-l', '-play', path])
                    break

                else:
                    skipped_exts.append(ext)

            else:
                if skipped_exts:
                    alert("""We don't know how to play %s publishes with %s extensions.""" % (
                        entity['sg_type'], '/'.join(sorted(skipped_exts))
                    ))
                else:
                    alert("""%s publish %d ("%s") has nothing to play.""" % (
                        entity['sg_type'].title(), entity['id'], entity['code']
                    ))
                return



    else:
        alert("We don't know how to play %s entities." % entity_type)
