from __future__ import absolute_import

import os

from . import base

from maya import cmds, mel


maya_version = int(mel.eval('about -version').split()[0])


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
    
    playback_slider = mel.eval('$tmpVar = $gPlayBackSlider')
    if not playback_slider:
        print '# Could not get gPlayBackSlider'
        return
    
    sound_node = cmds.timeControl(playback_slider, query=True, sound=True)
    if not sound_node:
        cmds.warning('No sound node.')
        return
    
    return cmds.sound(sound_node, query=True, file=True)


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
        publisher.metadata['maya'] = {
            'version': maya_version,
            'references': [str(x) for x in cmds.file(query=True, reference=True) or []],
            'sound_path': get_current_sound(),
            'min_time': cmds.playbackOptions(query=True, minTime=True),
            'max_time': cmds.playbackOptions(query=True, maxTime=True),
        }
    
    def promotion_fields(self, publisher, **kwargs):
        min_time = cmds.playbackOptions(query=True, minTime=True)
        max_time = cmds.playbackOptions(query=True, maxTime=True)
        return {
            'sg_first_frame': int(min_time),
            'sg_last_frame': int(max_time),
            'frame_count': int(max_time - min_time + 1),
        }

