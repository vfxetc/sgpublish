from __future__ import absolute_import

import os
import re
import sys

from sgfs.commands.utils import parse_spec
from sgfs import SGFS

from sgpublish import Publisher
from sgpublish.utils import has_pardir, strip_pardir


def basename(src_path):    
    basename = os.path.basename(src_path)
    basename = os.path.splitext(basename)[0]
    basename = re.sub(r'_*[rv]\d+', '', basename)
    return basename


def main(argv=None):

    import argparse

    parser = argparse.ArgumentParser()

    meta_group = parser.add_argument_group('shotgun meta', '''
        Metadata about this publish that only exists in Shotgun.
    ''')
    meta_group.add_argument('-l', '--link', required=True,
        help='the Shotgun entity to link this publish to, e.g. Shot:1234')
    meta_group.add_argument('-t', '--type', required=True,
        help='the type of publish; must exist in SGFS schema')
    meta_group.add_argument('-n', '--name', '--code',
        help='the name of the publish')
    meta_group.add_argument('-d', '--description', metavar='DESC',
        help='a description of the publish')
    meta_group.add_argument('-T', '--thumbnail', metavar='PATH',
        help='existing thumbnail to upload')

    path_group = parser.add_argument_group('publish relative paths', '''
        Paths that describe how to interpret different contents of the publish.
        If relative, they are relative to the final publish directory (and so
        should be relative to the current working directory or the path passed
        to `-C`). Absolute paths are used as is, but discouraged as they will
        be outside of the publish.
    ''')
    path_group.add_argument('-p', '--path', help='primary "path" of the publish')
    path_group.add_argument('--frames-path', metavar='PATH')
    path_group.add_argument('--movie-path', metavar='PATH')
    path_group.add_argument('--movie-url', metavar='PATH', help='URL to view a contained movie')

    input_group = parser.add_argument_group('inputs', '''
        The files to add to the publish, and how to structure them in the publish.
    ''')
    input_group.add_argument('-C', '--relative-to', metavar='PATH',
        help='absolute paths are interpreted as relative to this one; defaults to the current working directory',
        default=os.getcwd()
    )
    input_group.add_argument('files', nargs='+', help='the files to include in the publish')

    args = parser.parse_args(argv)


    sgfs = SGFS()
    link = parse_spec(sgfs, args.link)

    with Publisher(

        link=link,
        type=args.type,
        name=args.name or basename(args.files[0]),
        description=args.description,

        thumbnail_path=args.thumbnail,
        path=args.path,
        frames_path=args.frames_path,
        movie_path=args.movie_path,
        movie_url=args.movie_url,

    ) as publisher:
        for i, path in enumerate(args.files):

            # The publish will be structured relative to the given root
            # (or pwd if unset).
            rel_path = os.path.relpath(path, args.relative_to)

            if has_pardir(rel_path):
                print >> sys.stderr, 'WARNING: %s is not within %s' % (
                    path, args.relative_to
                )
                rel_path = strip_pardir(path)

            dst_path = publisher.add_file(path, rel_path)

            # Set the publish's "path" to that of the first file.
            if not i and args.path is None:
                publisher.path = dst_path


    print publisher.directory


if __name__ == '__main__':
    main()
