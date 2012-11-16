import subprocess
import platform


def call_open(x):
    if platform.system() == 'Darwin':
        subprocess.call(['open', x])
    else:
        subprocess.call(['xdg-open', x])
