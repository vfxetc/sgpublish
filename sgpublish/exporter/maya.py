from __future__ import absolute_import

import itertools
import os
import datetime
import threading

from mayatools.units import core as units
from maya import cmds, mel

import uifutures

from . import base
from sgpublish import utils


def maya_version():
    return int(mel.eval('about -version').split()[0])


def get_sound_for_frames(frames):
                
    if not frames.startswith('/var/tmp/srv_playblast'):
        return
    
    print '# Frames are from old playblast manager...'
                
    audio_meta_path = os.path.join(os.path.dirname(frames), 'audio.txt')
    if not os.path.exists(audio_meta_path):
        return
    
    audio_metadata = open(audio_meta_path).readlines()
    audio_metadata = [x.strip() for x in audio_metadata]
    audio_metadata = [x for x in audio_metadata if not x.startswith('#')]
    audio_metadata = [x for x in audio_metadata if x]
    
    if len(audio_metadata) > 1 and os.path.splitext(audio_metadata[1])[1][1:] in ('aif', 'aiff', 'wav'):
        print '# Found sound from old playblast manager.'
        return audio_metadata[1]


def get_current_sound():
    
    try:
        playback_slider = mel.eval('$tmpVar = $gPlayBackSlider')
    except RuntimeError:
        playback_slider = None
    if not playback_slider:
        print '# Could not get gPlayBackSlider'
        return
    
    sound_node = cmds.timeControl(playback_slider, query=True, sound=True)
    if not sound_node:
        cmds.warning('No sound node.')
        return
    
    sound_path = cmds.sound(sound_node, query=True, file=True)

    # Assert that it exists. It is a bit overkill to check it here, but all
    # we are doing is dumping it into the Maya log, so it isn't a big deal.
    if sound_path and os.path.exists(sound_path):
        return sound_path
    else:
        cmds.warning('Sound file (via node %s) at %s does not exist.' % (sound_node, sound_path))


class Exporter(base.Exporter):
    
    def __init__(self, *args, **kwargs):
        super(Exporter, self).__init__(*args, **kwargs)
    
    @property
    def filename_hint(self):
        return self._filename_hint or cmds.file(q=True, sceneName=True) or None
    
    @property
    def workspace(self):
        return self._workspace or cmds.workspace(query=True, rootDirectory=True) or os.getcwd()
    
    def get_previous_publish_ids(self):
        ids = cmds.fileInfo('sgpublish_%s_ids' % self.publish_type, query=True)
        return set(int(x.strip()) for x in ids[0].split(',')) if ids else set()
    
    def record_publish_id(self, id_):
        ids = self.get_previous_publish_ids()
        ids.add(id_)
        cmds.fileInfo('sgpublish_%s_ids' % self.publish_type, ','.join(str(x) for x in sorted(ids)))
    
    def before_export_publish(self, publisher, **kwargs):

        # Add a bunch of metadata.
        file_info = [x.encode('utf8') for x in cmds.fileInfo(q=True)]
        file_info = dict(zip(file_info[0::2], file_info[1::2]))

        publisher.metadata['maya'] = {
            'file_info': file_info,
            'max_time': cmds.playbackOptions(query=True, maxTime=True),
            'min_time': cmds.playbackOptions(query=True, minTime=True),
            'references': [str(x) for x in cmds.file(query=True, reference=True) or []],
            'sound_path': get_current_sound(),
            'version': maya_version(), # Redundant with file_info, but used historically.
        }

        # Playblasts should be converted into frames.
        if publisher.frames_path and not publisher.movie_path:
            
            movie_path = publisher.add_file('%s,v%04d.mov' % (publisher.name, publisher.version), method='placeholder')
        
            # Assert the directory exists.
            dir_ = os.path.dirname(movie_path)
            if not os.path.exists(dir_):
                os.makedirs(dir_)

            # Make the path unique.
            if os.path.exists(movie_path):
                base, ext = os.path.splitext(movie_path)
                for copy_i in itertools.count(1):
                    movie_path = '%s_%04d%s' % (base, copy_i, ext)
                    if not os.path.exists(movie_path):
                        break

            
            sound_path = get_sound_for_frames(publisher.frames_path) or get_current_sound()
            
            # Spawn the job.
            print '# Scheduling make_quicktime to %r from %r' % (movie_path, publisher.frames_path)
            if sound_path:
                print '# Sound from %r' % sound_path
            
            # FIXME: We are having a hard time with uifutures at Mark Media.
            if False:
                with uifutures.Executor() as executor:
                    executor.submit_ext(
                        func=utils.make_quicktime,
                        kwargs={
                            'movie_path': movie_path,
                            'frames_path': publisher.frames_path,
                            'audio_path': sound_path,
                            'framerate': units.get_fps(),
                        },
                        name="QuickTime \"%s_v%04d\"" % (publisher.name, publisher.version),
                    )
            else:
                # TODO: Add a progress bar.
                thread = threading.Thread(target=utils.make_quicktime, kwargs={
                    'movie_path': movie_path,
                    'frames_path': publisher.frames_path,
                    'audio_path': sound_path,
                    'framerate': units.get_fps(),
                })
                thread.start()

            # Finally set the Shotgun attributes.
            publisher.movie_path = movie_path
            publisher.frames_path = None
    
    def fields_for_review_version(self, **kwargs):
        min_time = cmds.playbackOptions(query=True, minTime=True)
        max_time = cmds.playbackOptions(query=True, maxTime=True)
        return {
            'sg_first_frame': int(min_time),
            'sg_last_frame': int(max_time),
            'frame_count': int(max_time - min_time + 1),
        }

