from __future__ import absolute_import

import functools
import threading
import time

from maya import cmds

import mayatools.shelf

from .core import check_paths


def __before_reload__():
    return register_hook._script_job, register_hook._thread_target
def __after_reload__(state):
    register_hook._script_job, register_hook._thread_target = state


class _update_thread_target(object):
    
    def __init__(self):
        self.stop = False
        self.delay = 5 * 60
    
    def __call__(self):
        while not self.stop:
            time.sleep(self.delay)
            if self.stop:
                break
            update_buttons()


def register_hook():
    
    if register_hook._script_job:
        cmds.scriptJob(kill=register_hook._script_job, force=True)
    if register_hook._thread_target:
        register_hook._thread_target.stop = True
    
    register_hook._script_job = cmds.scriptJob(event=('SceneOpened', update_buttons))
    
    register_hook._thread_target = _update_thread_target()
    register_hook._thread = threading.Thread(target=register_hook._thread_target)
    register_hook._thread.daemon = False
    register_hook._thread.start()
    
register_hook._script_job = None
register_hook._thread_target = None


def update_buttons():
    
    print 'setting to yello'
    # Reset to yellow
    for button in mayatools.shelf.buttons_from_uuid('sgpublish.ui.maya.update_references:run'):
        print button['name']
        cmds.shelfButton(button['name'], edit=True, image='publishes/check_deps_unknown.png')
    
    # Spawn a job.
    threading.Thread(target=_update_thread_target).start()
    
def _update_thread_target():
    time.sleep(1)
    cmds.scriptJob(idleEvent=functools.partial(_update_script_job, True), runOnce=True)
    
def _update_script_job(good):
    print 'setting to', good
    for button in mayatools.shelf.buttons_from_uuid('sgpublish.ui.maya.update_references:run'):
        cmds.shelfButton(button['name'], edit=True,
            image='publishes/check_deps_ok.png' if good else 'publishes/check_deps_bad.png')

