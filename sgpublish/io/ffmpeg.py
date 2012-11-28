import glob
import multiprocessing
import multiprocessing.dummy
import os
import Queue
import re
import subprocess
import sys
import threading
import time

import OpenEXR

from uifutures.worker import set_progress, notify

import ks.core.project

__also_reload__ = ['uifutures.worker']


def exrDataWindowCrop(path):
   
    
    f = OpenEXR.InputFile(path)
    header = f.header()
    f.close()
    dataWindow = header['dataWindow']
    crop_width = dataWindow.max.x - dataWindow.min.x + 1
    crop_height = dataWindow.max.y - dataWindow.min.y + 1
    
    
    crop = '%ix%i+%i+%i' % (crop_width,crop_height,dataWindow.min.x,dataWindow.min.y)
    
    return crop
    #md = ['']
    
    
def stderr_watcher(stderr,queue):
    
    line = ''
    while True:
        l = stderr.read(1)
        #print line
        if not l:
            break
    
        queue.put(l)
        
        #time.sleep(.5)
        
def print_queue(queue):
    
    data = ''
    try:
        while 1:
            l = queue.get_nowait()
            
            #print l
            data += l
        
    except Queue.Empty:
        pass
    if data:
        output = []
        progress = []

        for line in data.splitlines():
            
            if line.count('frame=') and line.count('time='):
                progress.append(line)
            else:
                output.append(line)
                
        if progress:
            output.append(progress[-1])  
            
        print '\n'.join(output)
        

class Imagemagick(object):
    
    def __init__(self):
        self.size = '1280x720'
        
        self.lut = None
        
        
    def conform(self,path,dest='pnm:-',stdin=None):
        
        size = self.size
        
        lut = self.lut
        
        name,ext = os.path.splitext(path)
        crop = None
        if ext.lower() in ['.exr']:
            
            crop = exrDataWindowCrop(path)

        
        cmd = ['convert', path]
        
        

        if crop:
         
   
            cmd.extend(['-crop',crop])
        
        
        cmd.extend([ '-background','black','-flatten','-gravity', 'Center', '-resize', str(size) ,'-depth','8', '-strip','-extent',str(size),'+matte'])
        
        if lut:
            cmd.extend([lut,'-hald-clut'])
            

        cmd.extend([dest])
        
        #print subprocess.list2cmdline(cmd)
        
        
        p = subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        
        stdout,stderr = p.communicate(stdin)
        
        returncode = p.returncode
        if returncode != 0:
            print subprocess.list2cmdline(cmd)
            raise Exception(stderr)
            #print stderr
        
        return stdout,stderr,returncode

        #print path
    
def get_image_data(args):
    path = args[0]
    
    size = args[1]
    lut = args[2]
    
    magick = Imagemagick()
    magick.size = size
    magick.lut = lut
    
    data = magick.conform(path)
    
    return data
    
    



class FFmpeg(object):
    
    def __init__(self):
        self.vcodec = ['-vcodec', 'libx264','-pix_fmt','yuv420p', '-profile','baseline', '-crf', '20']
        self.acodec = None
        
        self.size = '1280x720'
        
        self.fps = '23.97'
        

    def quicktime_from_image_sequence(self,imagelist,dest,lut=None):
        
        
        vcodec = self.vcodec
        fps = str(self.fps)
        
        size = self.size
        
       
        
        cmd = ['ffmpeg', '-y', '-vcodec', 'ppm','-r',fps, '-f', 'image2pipe','-i', '-']
        
        cmd.extend(vcodec)
        cmd.extend(['-r',fps, dest])
        

        #process_count = min(6,multiprocessing.cpu_count())
        process_count = multiprocessing.cpu_count()/2
        #process_count = multiprocessing.cpu_count() 
        #pool = multiprocessing.dummy.Pool(process_count)
        pool = multiprocessing.Pool(process_count)
        
        args = []
        for i,item in enumerate(imagelist):
            

            args.append([item,size,lut])
            
            
        result = pool.imap(get_image_data,args)
        
        p =None
        thread = None
        
        count = len(imagelist)
        q = Queue.Queue()
        t = time.time()
        for i, data in enumerate(result):
            
            
            #
            
            stdout = data[0]
            stderr = data[1]
            
            ret = data[2]
            
            
            
            if not p:
                p = subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE,stdout=subprocess.PIPE,close_fds=True)
                
                thread = threading.Thread(target=stderr_watcher,args=(p.stderr,q))
                thread.start()
                t = time.time()
                
            p.stdin.write(stdout)
            p.stdin.flush()
            
            set_progress(value=i, maximum=count)
            
            if time.time() - t > 1:
                print '%04d/%04d' % (i, count)
                print_queue(q)
                t = time.time()
            
        p.stdin.close()
        
        
        
        pool.close()
        pool.join()
        
        if thread:
            thread.join()
            
        print_queue(q)
        
        notify(message='Your quicktime is done!')


def quicktime_from_glob(mov_path, pattern, lut=None):
    
    # Get an actual file name out of a pattern.
    if '#' in pattern:
        pattern = re.sub('#+', '*', pattern)
    if '*' in pattern:
        pattern = sorted(glob.glob(pattern))[0]
    
    # Read in the sequence.
    # TODO: Rebuild this functionality.
    sequence = ks.core.project.get_sequence(pattern)
    
    # Do the conversion.
    FFmpeg().quicktime_from_image_sequence(sequence, mov_path, lut)


if __name__ == '__main__':
    quicktime_from_glob(sys.argv[1], sys.argv[2])



