import functools
import logging
import re

from sgsession import Session


def get_related_publishes(to_check, fields=()):
    """Find all publishes which derive from the given ones.

    Looks in ``sg_source_publishes`` field of ``PublishEvent`` for any of
    the given publishes.

    :param list to_check: List of publish entities.
    :param list fields: Extra fields to fetch on derived publishes.
    :return: ``set`` of publish entities.

    """

    if not isinstance(to_check, (list, tuple)):
        to_check = [to_check]

    assert all(x['type'] == 'PublishEvent' for x in to_check)

    sg = to_check[0].session
    fields = tuple(fields) + ('source_publishes', )

    seen = set()
    related = set()

    while True:

        # Filter out those we have already looked at.
        to_check = [x for x in to_check if x not in seen]
        seen.update(to_check)

        if not to_check:
            break

        checking = to_check
        to_check = []

        # Find all sources of these publishes.
        sg.fetch(checking, ['source_publishes'])
        for x in checking:
            to_check.extend(x['source_publishes'] or ())

        # Find any that these are the source of.
        to_check.extend(sg.find('PublishEvent', [('source_publishes', 'in', checking)], fields))

        related.update(to_check)

    return related


def _split_to_set(x):
    if isinstance(x, set):
        return x
    elif isinstance(x, basestring):
        return set(re.split(r'\W+', x))
    elif x is None:
        return set()
    else:
        return set(x)


class RepublishEventPlugin(object):

    def __init__(self, **kwargs):

        self._funcs = []
        self._dispatcher_kwargs = kwargs
        kwargs.setdefault('callback_in_subprocess', False)

        if 'name' in kwargs:
            self.log = logging.getLogger(kwargs['name'])
        else:
            name = kwargs.setdefault('name', self.__class__.__name__)
            self.log = logging.getLogger('%s:%s' % (__name__, self.name))

    def register(self, src_types, dst_types, src_steps=None, func=None, args=None, kwargs=None):

        if func is None:
            return functools.partial(self.register, src_types, dst_types, src_steps,
                args=args, kwargs=kwargs,
            )

        src_types = _split_to_set(src_types)
        dst_types = _split_to_set(dst_types)
        src_steps = _split_to_set(src_steps)
        
        if not dst_types:
            raise ValueError('must provide destination types for idempodence checks')

        self._funcs.append((src_types, dst_types, src_steps, func, args, kwargs))

    def __call__(self, dispatcher):
        dispatcher.register_callback(
            callback=self.handle_event,
            filter={
                'event_type': 'Shotgun_PublishEvent_Change',
                'attribute_name': 'sg_version',
            },
            **self._dispatcher_kwargs
        )

    def handle_event(self, event):

        # Must be setting it to a non-zero version.
        # NOTE: We MUST check the meta for this, otherwise we are liable to
        # schedule this job multiple times as the `entity` field is always
        # up to date.
        version = event.meta.get('new_value')
        if not version:
            self.log.debug('Publish is still being created; skipping')
            return

        # Make a clean one every time so that we don't slowly fill up memory.
        sg = Session()
        
        publish = sg.merge(event)['entity']
        if not publish:
            self.log.warning('Publish appears to have been deleted; skipping')
            return
            
        _, login, step_code, publish_type = publish.fetch((
            'code',
            'created_by.HumanUser.login',
            'sg_link.Task.step.Step.short_name',
            'sg_type',
        ))

        related = None

        for src_types, dst_types, src_steps, func, args, kwargs in self._funcs:

            # Make sure it is the right type.
            if publish_type not in src_types:
                self.log.debug('sg_type %r is not %s; skipping' % (publish_type, '/'.join(sorted(src_types))))
                continue

            # Make sure it is from the correct step.
            # Steps names could use some love...
            if src_steps and step_code not in src_steps:
                self.log.debug('sg_link.step.short_code %s is not %s; skipping' % (step_code, '/'.join(sorted(src_steps))))
                continue

            # Make sure we haven't already derived it, or are in progress of
            # deriving it.
            if related is None:
                related = get_related_publishes(publish, fields=['code', 'sg_type'])
            skip = False
            for x in related:
                if x['sg_type'] in dst_types:
                    self.log.warning('Derived %s publish %d "%s", already exists; skipping' % (
                        x['sg_type'], x['id'], x['code'],
                    ))
                    skip = True
            if skip:
                continue

            # If it is a string, dispatch it to Qube.
            if isinstance(func, basestring):

                # Run it as the correct user; assume their Shotgun login matches.
                login = publish.get('created_by.HumanUser.login')
                user = login.split('@')[0] if login else None

                qube_args = [publish.minimal]
                qube_args.extend(args or ())

                qube_name = 'Republish %s %s "%s" as %s' % (
                    publish['sg_type'], publish['id'], publish['code'],
                    '/'.join(sorted(dst_types))
                )

                import qbfutures
                future = qbfutures.submit_ext(func,
                    args=qube_args,
                    kwargs=kwargs or {},
                    name=qube_name,
                    user=user,
                    priority=8000,
                )

                self.log.info('Qube job %d: %s' % (future.job_id, qube_name))

            else:
                func(publish, *(args or ()), **(kwargs or {}))

            # Only run the first one!
            return


