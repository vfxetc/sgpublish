import os
import re
import re
import glob


def strip_version(name):
    return re.sub(r'_v\d+(_r\d+)', '', name)


def get_next_revision(directory, basename, ext, version, revision=1):
    basename = strip_version(basename)
    pattern = re.compile(r'%s_v%04d_r(\d+)' % (re.escape(basename), version))
    for name in os.listdir(directory):
        m = pattern.match(name)
        if m:
            revision = max(revision, int(m.group(1)) + 1)
    return revision


def get_next_revision_path(directory, basename, ext, version, revision=1):
    basename = strip_version(basename)
    revision = get_next_revision(directory, basename, ext, version, revision)
    return os.path.join(directory, '%s_v%04d_r%04d%s' % (basename, version, revision, ext))


def make_quicktime(movie_path, frames_path, audio_path=None):
    
    from uifutures.worker import set_progress, notify

    import ks.core.project
    import ks.core.quicktime.quicktime
    
    # Get an actual file name out of a pattern.
    if '#' in frames_path:
        frames_path = re.sub('#+', '*', frames_path)
    if '*' in frames_path:
        frames_path = sorted(glob.glob(frames_path))[0]
    
    # Read in the sequence.
    # TODO: Rebuild this functionality.
    frame_sequence = ks.core.project.get_sequence(frames_path)
    
    qt = ks.core.quicktime.quicktime.quicktime()
    
    # Setup signal to the user.
    qt.progress = lambda value, maximum: set_progress(value, maximum)
    
    # Process it.
    qt.make_quicktime(frame_sequence, movie_path)
    
    notify('Your QuickTime is done.')