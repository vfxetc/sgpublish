import os
from setuptools import setup, find_packages

setup(
    name='sgpublish',
    version='0.1.0b',
    description='Shotgun publishes.',
    url='http://github.com/westernx/sgpublish',
    
    packages=find_packages(exclude=['build*', 'tests*']),
    include_package_data=True,

    author='Mike Boers',
    author_email='sgpublish@mikeboers.com',
    license='BSD-3',
    
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    
)