from __future__ import absolute_import

# All imports should be in a function so that they do not polute the global
# namespace, except for `from maya import cmds` because we want that everywhere.
from maya import cmds, OpenMaya


def standard_setup():
    """Non-standalone user setup."""
    
    # Setup background check every time a new scene is opened.
    def check_references(*args):
        import metatools.imports
        import sgpublish.check.maya
        metatools.imports.autoreload(sgpublish.check.maya)
        sgpublish.check.maya.start_background_check()

    for name, type_ in [

        ('after_open', OpenMaya.MSceneMessage.kAfterOpen),

        # TODO: Re-enable this one when we know the general uitools.threads stuff
        # is stable, since a crash while saving is tremendously bad.

        # ('after_save', OpenMaya.MSceneMessage.kAfterSave),

        # We used to have kAfterCreateRererence and kAfterLoadReference in here
        # too, but for now it is
        # a relatively corner case for it to not be paired with creating a
        # reference, and the logic is clever enough to stack several update
        # requests together.

    ]:
        __mayatools_usersetup__['name'] = OpenMaya.MSceneMessage.addCallback(
            type_,
            check_references,
        )


    # Setup background check every 5 minutes.
    try:
        from uitools.qt import QtCore
        import sgpublish.check.maya
    except ImportError as e:
        print '[sgpublish] Missing dependency:', e
    else:
        __mayatools_usersetup__['timer'] = timer = QtCore.QTimer()
        timer.timeout.connect(sgpublish.check.maya.start_background_check)
        timer.setInterval(1000 * 60 * 5) # Every 5 minutes.
        timer.start()


# Block from running the production userSetup if the dev one already ran.
if not '__mayatools_usersetup__' in globals():
    __mayatools_usersetup__ = {}

    # Most things should not run in batch mode.
    if not cmds.about(batch=True):
        standard_setup()


# Cleanup the namespace.
del standard_setup
