from common import *


    
class TestBasicPublisher(TestCase):
    
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
        
        self = None
    
    def test_basic_publish(self):
        
        scene_path = os.path.join(self.sandbox, 'test_scene.ma')
        open(scene_path, 'w').write('this is a dummy scene')
        
        with Publisher(name='test_scene', type="maya_scene", link=self.task, sgfs=self.sgfs) as publisher:
            publisher.add_file(scene_path)
        
        print publisher.path

        publish = self.session.find_one('PublishEvent', [('id', 'is', publisher.entity['id'])])
        self.assertTrue(publish is not None)
        self.assertEqual(publish.fetch('code'), 'test_scene')

    def test_publish_sources(self):

        data_file = os.path.join(self.sandbox, 'data_file.txt')
        open(data_file, 'w').write('this is a dummy file')

        with Publisher(name='test_publish_source', type='generic', link=self.task, sgfs=self.sgfs) as publisher:
            published_file = publisher.add_file(data_file)

        self.assertTrue(os.path.basename(published_file), 'data_file.txt')
        source = publisher.entity

        # Now some event happens.

        with Publisher(name='test_republish_from_event', type='republish', link=self.task, sgfs=self.sgfs,
            source_publishes=[source], trigger_event={'type': 'xxx', 'id': 1234}
        ) as publisher:
            republished_file = publisher.add_file(published_file)

        self.assertTrue(os.path.basename(republished_file), 'data_file.txt')
        republish = publisher.entity

        self.assertEqual(republish.fetch('sg_source_publishes'), [source])
        self.assertEqual(republish.fetch('sg_trigger_event_id'), 1234)

    def test_publish_template(self):
        pass
        

