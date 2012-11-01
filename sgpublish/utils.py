import os

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