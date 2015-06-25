from __future__ import absolute_import

import os
import re

from sgfs.commands.utils import parse_spec
from sgfs import SGFS

from sgpublish import utils
from sgpublish import Publisher


def basename(src_path):    
    basename = os.path.basename(src_path)
    basename = os.path.splitext(basename)[0]
    basename = re.sub(r'_*[rv]\d+', '', basename)
    return basename


def main(argv=None):

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--link', required=True)
    parser.add_argument('-t', '--type', required=True)
    parser.add_argument('-n', '--name', '--code')
    parser.add_argument('-T', '--thumbnail')
    parser.add_argument('files', nargs='+')
    args = parser.parse_args(argv)

    sgfs = SGFS()
    link = parse_spec(sgfs, args.link)

    with Publisher(
        link=link,
        type=args.type,
        name=args.name or basename(args.files[0]),
        thumbnail_path=args.thumbnail,
    ) as publisher:
        for i, path in enumerate(args.files):
            dst_path = publisher.add_file(path)
            if not i:
                publisher.path = dst_path

    print publisher.directory


if __name__ == '__main__':
    main()
