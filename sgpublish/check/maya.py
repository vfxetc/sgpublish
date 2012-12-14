from __future__ import absolute_import

import functools
import threading
import time

from maya import cmds

import mayatools.shelf
from uitools.threads import defer_to_main_thread, call_in_main_thread

from .core import check_paths


_issued_warnings = set()
_check_lock = threading.Lock()

def start_background_check(*args):
    print '# Starting publish background check...'
    defer_to_main_thread(_update_buttons, None)
    references = call_in_main_thread(cmds.file, q=True, reference=True)
    threading.Thread(target=_background_check, args=[references]).start()


def _background_check(references):

    with _check_lock:

        statuses = check_paths(references, only_published=True)
        if not statuses:
            print '# No publishes are referenced.'
            defer_to_main_thread(_update_buttons, True)
            return

        out_of_date = []
        good = 0
        for status in statuses:
            if status.is_latest:
                good += 1
            else:
                out_of_date.append(status)

        if not out_of_date:
            print '# None of the %d publishes are out of date.' % good
            defer_to_main_thread(_update_buttons, True)
            return

        print '# %d publishes are out of date.' % len(out_of_date)
        defer_to_main_thread(_update_buttons, False)

    
def _update_buttons(status):
    image = {
        None: 'publishes/check_deps_unknown.png',
        True: 'publishes/check_deps_ok.png',
        False: 'publishes/check_deps_bad.png'
    }[status]
    print '# Setting button image to', image
    for button in mayatools.shelf.buttons_from_uuid('sgpublish.mayatools.update_references:run'):
        cmds.shelfButton(button['name'], edit=True, image=image)

