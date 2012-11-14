import os
import re

import shotgun_api3_registry


def guess_shotgun_user():
    """Guess Shotgun user from current login name.
    
    Looks for a user with an email that has the login name as the account.
    
    :returns: ``dict`` of ``HumanUser``, or ``None``.
    
    """
    
    # Memoize this, so that we only do it once.
    try:
        return guess_shotgun_user._result
    except AttributeError:
        pass

    shotgun = shotgun_api3_registry.connect(name='sgpublish')
    login = os.getlogin()
    human = shotgun.find_one('HumanUser', [('email', 'starts_with', login + '@')])
    
    guess_shotgun_user._result = human
    return human


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
    