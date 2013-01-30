from maya import cmds

from common import *

from uitools.trampoline import sleep
from metatools.imports import autoreload
from sgpublish.mayatools import publish_scene


class TestMayaScenePublish(TestCase):

    @requires_maya(gui=True)
    def setUp(self):
        autoreload(publish_scene)
        cmds.file(new=True, force=True)

    @requires_maya(gui=True)
    def test_scene_publish(self):

        dialog = publish_scene.run(testing=True)
        self.assertTrue(dialog is not None)

        widget = dialog._publishWidget
        self.assertTrue(widget is not None)

        # Wait for it to get data.
        sleep(1)

        widget._name_field.setText('Publish_Test')
        widget._description.setText('This is just a test.')
        dialog._on_submit()
        
