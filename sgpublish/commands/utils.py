import os

from sgfs.commands.utils import parse_spec
from sgfs import SGFS


def add_publisher_arguments(parser, short_flags=True, prefix=None):

    if prefix and not isinstance(prefix, basestring):
        prefix = 'publish'

    def add_argument(x, *flags, **kwargs):

        args = []
        first_long_flag = None
        has_flag = False

        for flag in flags:

            is_flag = flag.startswith('-')
            is_long = flag.startswith('--')
            has_flag = has_flag or is_flag

            # We use the first long flag for dest and metavar.
            if is_long or not is_flag:
                first_long_flag = first_long_flag or flag

            # Short flags.
            if is_flag and not is_long:
                if short_flags:
                    args.append(flag)
                continue

            if prefix:
                flag = ('--' if is_flag else '') + prefix.strip('-') + '-' + flag.strip('-')
            else:
                flag = ('--' if is_flag else '') + flag.strip('-')

            args.append(flag)

        if has_flag and 'dest' not in kwargs:
            kwargs['dest'] = 'publisher_' + (first_long_flag or flags[0]).strip('-').replace('-', '_')
        if 'metavar' not in kwargs:
            kwargs['metavar'] = (first_long_flag or flags[0]).strip('-').replace('-', '_').upper()

        x.add_argument(*args, **kwargs)

    group = parser.add_argument_group('publisher', '''
        For the creation of publishes.
    ''')

    meta_group = group.add_argument_group('shotgun meta', '''
        Metadata about this publish that only exists in Shotgun.
    ''')

    add_argument(meta_group, '--template', metavar='ID',
        help='existing PublishEvent to copy attributes from')
    add_argument(meta_group, '-l', '--link',
        help='the Shotgun entity to link this publish to, e.g. Shot:1234')
    add_argument(meta_group, '-t', '--type',
        help='the type of publish; must exist in SGFS schema')
    add_argument(meta_group, '-n', '--name', '--code',
        help='the name of the publish')
    add_argument(meta_group, '-d', '--description', metavar='DESC',
        help='a description of the publish')
    add_argument(meta_group, '-T', '--thumbnail', metavar='PATH',
        dest='publisher_thumbnail_path',
        help='existing thumbnail to upload')

    path_group = group.add_argument_group('publish relative paths', '''
        Paths that describe how to interpret different contents of the publish.
        If relative, they are relative to the final publish directory (and so
        should be relative to the current working directory or the path passed
        to `-C`). Absolute paths are used as is, but discouraged as they will
        be outside of the publish.
    ''')
    add_argument(path_group, '-p', '--path', help='primary "path" of the publish')
    add_argument(path_group, '--frames-path', metavar='PATH')
    add_argument(path_group, '--movie-path', metavar='PATH')
    add_argument(path_group, '--movie-url', metavar='PATH', help='URL to view a contained movie')


def extract_publisher_kwargs(args, sgfs=None):

    kwargs = {key[10:]: value for key, value in args.__dict__.iteritems() if key.startswith('publisher_')}

    sgfs = sgfs or SGFS()
    if kwargs['link']:
        kwargs['link'] = parse_spec(sgfs, kwargs['link'])
    if kwargs['template']:
        kwargs['template'] = parse_spec(sgfs, kwargs['template'], entity_types=['PublishEvent'])

    return kwargs



