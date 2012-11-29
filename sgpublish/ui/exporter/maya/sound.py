import os

from maya import cmds, mel

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