import os

from sgfs.commands.utils import parse_spec
from sgfs import SGFS


def default_sort_key(publish):
    return publish['sg_version'], publish['created_at']


def parse_as_publish(sgfs, input_, publish_types=None, search_for_publish=True, filters=(), fields=(), sort_key=None):
    """Given input from a user, find a publish.

    When searching, publishes are sorted by with ``sort_key``, and the last
    one is taken. The default ``sort_key`` sorts by ``(version, created_at)``.

    """

    if isinstance(input_, basestring):
        input_ = parse_spec(sgfs, input_)

    if publish_types and isinstance(publish_types, basestring):
        publish_types = [publish_types]

    if input_['type'] == 'PublishEvent':
        publish = input_
        if publish_types and publish.fetch('sg_type') not in publish_types:
            raise ValueError('PublishEvent is %s, should be in %r' % (publish['sg_type'], tuple(sorted(publish_types))))
        return publish

    if not search_for_publish:
        raise ValueError('no publish from input')

    base_filters = list(filters or ())
    base_fields = list(fields or ()) + (['sg_version', 'created_at'] if sort_key is None else [])
    if publish_types:
        base_filters.append(('sg_type', 'in', tuple(publish_types)))

    if input_['type'] == 'Task':
        publishes = sgfs.session.find('PublishEvent', base_filters + [
            ('sg_link', 'is', input_),
        ], base_fields)
    elif input_['type'] in ('Shot', 'Asset'):
        publishes = sgfs.session.find('PublishEvent', base_filters + [
            ('sg_link.Task.entity', 'is', input_),
        ], base_fields)
    else:
        raise ValueError('cannot find publishes from %s' % input_['type'])

    if not publishes:
        raise ValueError('no publishes on {type} {id}'.format(**input_))

    publishes.sort(key=sort_key or default_sort_key)
    return publishes[-1]


def parse_as_path_or_publish(sgfs, input_, file_exts=None, fields=(), **kwargs):

    if isinstance(file_exts, basestring):
        file_exts = (file_exts, )

    path = publish = None

    # Check the path (which is either the input string, or the magic __path__
    # field that may be set by parse_spec).
    potential_path = input_ if isinstance(input_, basestring) else input_.get('__path__')
    if potential_path and os.path.exists(potential_path):
        if not file_exts or os.path.splitext(potential_path)[1] in file_exts:
            path = potential_path

    # Also go looking for a publish that contains that path.
    fields = list(fields or ()) + ['sg_path']
    try:
        publish = parse_as_publish(sgfs, input_, fields=fields, **kwargs)
    except ValueError:
        if not path:
            raise

    # The user gave us a path which exists, return it with whatever publish we
    # may have found.
    if path:
        return path, publish

    if 'sg_path' not in publish:
        publish.fetch(fields) # Grab them all, but only if we don't have our one.
    path = publish['sg_path']
    if not path:
        raise ValueError('publish %s has no path' % publish['id'])
    if file_exts and os.path.splitext(path)[1] not in file_exts:
        raise ValueError('publish %d path\'s ext not %s' % (publish['id'], '/'.join(sorted(file_exts))))
    return path, publish



def add_publisher_arguments(parser, short_flags=True, prefix=None, skip=frozenset()):

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

            if flag.strip('-') in skip:
                return

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

    group = parser.add_argument_group('Publishing', '''
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
    add_argument(meta_group, '-V', '--version', type=int,
        help='the version of the publish')
    add_argument(meta_group, '-d', '--description', metavar='DESC',
        help='a description of the publish')
    add_argument(meta_group, '-T', '--thumbnail', metavar='PATH',
        dest='publisher_thumbnail_path',
        help='existing thumbnail to upload')

    if 'paths' not in skip:
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


def extract_publisher_kwargs(args, sgfs=None, delete=True):

    kwargs = {}

    for key, value in args.__dict__.items():
        if key.startswith('publisher_'):
            if value is not None:
                kwargs[key[10:]] = value
            if delete:
                delattr(args, key)

    sgfs = sgfs or SGFS()
    if 'link' in kwargs:
        kwargs['link'] = parse_spec(sgfs, kwargs['link'])
    if 'template' in kwargs:
        kwargs['template'] = parse_spec(sgfs, kwargs['template'], entity_types=['PublishEvent'])

    return kwargs
