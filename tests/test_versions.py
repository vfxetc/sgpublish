from common import *

from sgpublish import versions


class TestVersions(TestCase):
    
    def setUp(self):
        
        sg = Shotgun()
        self.sg = self.fix = fix = Fixture(sg)
        
        self.proj_name = 'Test Project ' + mini_uuid()
        proj = fix.Project(self.proj_name)
        seq = proj.Sequence('AA', project=proj)
        shot = seq.Shot('AA_001', project=proj)
        step = fix.find_or_create('Step', code='Anm', short_name='Anm')
        task = shot.Task('Animate Something', step=step, entity=shot, project=proj)
        
        self.proj = minimal(proj)
        self.seq = minimal(seq)
        self.shot = minimal(shot)
        self.step = minimal(step)
        self.task = minimal(task)

        self.session = Session(self.sg)
        self.sgfs = SGFS(root=self.sandbox, session=self.session, schema_name='testing')
        
        self.sgfs.create_structure([self.task], allow_project=True)
        
        self = None # For GC (?)
    
    def test_promote_one(self):
        
        scene_path = os.path.join(self.sandbox, 'test_scene.ma')
        open(scene_path, 'w').write('this is a dummy scene')
        
        with Publisher(name='test_scene', type="maya_scene", link=self.task, sgfs=self.sgfs) as publisher:
            publisher.add_file(scene_path)
        
        publish = publisher.entity
        version = versions.create_version_from_publish(publish, {}, sgfs=self.sgfs)

        self.assertEqual(publish['sg_version'], 1)
        self.assertEqual(publish['code'], 'test_scene')

        self.assertEqual(version['code'], 'test_scene_v0001')

        # TODO: There is a LOT more to assert here, but at least it ran!

    def test_promote_many(self):

        scene_path = os.path.join(self.sandbox, 'test_scene.ma')
        open(scene_path, 'w').write('this is a dummy scene')
        
        with Publisher(name='test_scene', type="maya_scene", link=self.task, sgfs=self.sgfs) as publisher:
            publisher.add_file(scene_path)
        
        publish = publisher.entity
        entities = versions.create_versions_for_publish(publish, [
            dict(code='version_a', sg_path_to_movie='/path/to/a.mov'),
            dict(code='version_b', sg_path_to_movie='/path/to/b.mov'),
        ], sgfs=self.sgfs)

        self.assertEqual(publish['sg_version'], 1)
        self.assertEqual(publish['code'], 'test_scene')

        self.assertEqual(entities[0]['code'], 'version_a')
        self.assertEqual(entities[1]['code'], 'version_b')
        self.assertEqual(entities[0]['sg_path_to_movie'], '/path/to/a.mov')
        self.assertEqual(entities[1]['sg_path_to_movie'], '/path/to/b.mov')

        # TODO: There is a LOT more to assert here, but at least it ran!

