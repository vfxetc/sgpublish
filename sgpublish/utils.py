import os
import re
import re
import glob
from shutil import copy


def strip_version(name):
    return re.sub(r'_v\d+(_r\d+)', '', name)

def basename(src_path):    
    basename = os.path.basename(src_path)
    basename = os.path.splitext(basename)[0]
    basename = re.sub(r'_*[rv]\d+', '', basename)
    return basename

def get_next_revision(directory, basename, ext, version, revision=1):
    basename = strip_version(basename)
    pattern = re.compile(r'%s_v%04d_r(\d+)%s' % (re.escape(basename), version, re.escape(ext)))
    for name in os.listdir(directory):
        m = pattern.match(name)
        if m:
            revision = max(revision, int(m.group(1)) + 1)
    return revision


def get_next_revision_path(directory, basename, ext, version, revision=1):
    basename = strip_version(basename)
    revision = get_next_revision(directory, basename, ext, version, revision)
    return os.path.join(directory, '%s_v%04d_r%04d%s' % (basename, version, revision, ext))


_pardir_pattern = r'^((%s|%s)%s)+' % (re.escape(os.pardir), re.escape(os.curdir), re.escape(os.sep))

def has_pardir(path):
    return re.match(_pardir_pattern, path) is not None

def strip_pardir(path):
    """Remove parent/current directory markers from a path.

    >>> strip_pardir('.././a')
    'a'

    """
    return re.sub(_pardir_pattern, '', path)


def make_quicktime(movie_paths, frames_path, audio_path = None, extended_data = None):
    
    from uifutures.worker import set_progress, notify

    from dailymaker import dailymaker
    from dailymaker import utils as daily_utils
    from dailymaker import presets

    if isinstance(movie_paths, basestring):
        movie_paths = [movie_paths]
    movie_path = movie_paths[0]

    frame_sequence = daily_utils.parse_source_path(frames_path)

    qt = dailymaker.DailyMaker()
    qt.image_sequence = frame_sequence
    qt.source = frames_path
    qt.dest = movie_path
    qt.render_preview = False
    qt.extended_data = extended_data

    qt.set_preset(presets.find_preset(presets.get_default_preset()))

    # Setup signal to the user.
    qt._progress_callback = lambda value, maximum, image: set_progress(value, maximum, status = "Encoding %s" % os.path.basename(frame_sequence[value]))

    if audio_path:
        qt.audio = audio_path

    # Process it.
    qt.start()
    
    for extra_path in movie_paths[1:]:
        set_progress(status="Copying to %s" % os.path.dirname(extra_path))
        copy(movie_path, extra_path)

    notify('Your QuickTime is ready.')

