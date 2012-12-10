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
        
        with Publisher(name='test_scene', type="maya_scene", link=self.task, sgfs=self.sgfs) as publish:
            publish.add_file(scene_path)
        
        print publish.path
        
        
        