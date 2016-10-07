import errno
import os
import re
import re
import glob
from shutil import copy
import subprocess


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


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


def make_quicktime(movie_paths, frames_path, frames_per_second, audio_path=None, extended_data=None, progress_callback=None):
    
    from uifutures.worker import set_progress, notify

    if isinstance(movie_paths, basestring):
        movie_paths = [movie_paths]
    movie_path = movie_paths[0]

    # Replace #### with %04d
    frames_path = re.sub(r'(#+)', lambda m: '%%0%dd' % len(m.group(1)), frames_path)

    cmd = ['ffmpeg', '-framerate', frames_per_second, '-i', frames_path]
    if audio_path:
        cmd.extend(['-i', audio_path])
    cmd.extend([
        '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'baseline',
            '-crf', '22',
            '-threads', '0'
    ])
    if audio_path:
        cmd.extend([
            '-c:a', 'pcm_s24le',
        ])
    cmd.extend([
        movie_path
    ])

    subprocess.check_call(cmd)
    notify('Your QuickTime is ready.')
    return

    # Is this still a thing?
    for extra_path in movie_paths[1:]:
        set_progress(status="Copying to %s" % os.path.dirname(extra_path))
        copy(movie_path, extra_path)


