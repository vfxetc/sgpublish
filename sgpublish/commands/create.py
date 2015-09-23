from __future__ import absolute_import

import argparse
import os

from ..publisher import Publisher
from ..utils import basename
from .utils import add_publisher_arguments, extract_publisher_kwargs

def main(argv=None):

    parser = argparse.ArgumentParser()
    add_publisher_arguments(parser)

    input_group = parser.add_argument_group('inputs', '''
        The files to add to the publish, and how to structure them in the publish.
    ''')
    input_group.add_argument('-C', '--relative-to', metavar='PATH',
        help='absolute paths are interpreted as relative to this one; defaults to the current working directory',
        default=os.getcwd())
    input_group.add_argument('files', nargs='+',
        help='the files to include in the publish')

    args = parser.parse_args(argv)
    kwargs = extract_publisher_kwargs(args)

    if not kwargs['name']:
        kwargs['name'] = basename(args.files[0])

    with Publisher(**kwargs) as publisher:
        publisher.add_files(args.files, args.relative_to)

    print publisher.directory


if __name__ == '__main__':
    main()
