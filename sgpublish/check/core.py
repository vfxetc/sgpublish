import collections

from sgfs import SGFS


ReferenceStatus = collections.namedtuple('ReferenceStatus', ('path', 'used', 'latest', 'is_latest', 'all'))


def check_paths(paths, only_published=True):
    
    sgfs = SGFS()
    res = []
    
    for path in paths:
        
        publishes = sgfs.entities_from_path(path, 'PublishEvent')
        if only_published and not publishes:
            continue

        publish = publishes[0] if publishes else None
        if publish:

            siblings = sgfs.session.find('PublishEvent', [
                ('sg_link', 'is', publish['sg_link']),
                ('code', 'is', publish['code']),
                ('sg_type', 'is', publish['sg_type']),
            ], ['sg_path'])
            siblings.sort(key=lambda x: x['sg_version'])
            latest = max(siblings, key=lambda pub: pub['sg_version'])

        else:
            siblings = []
            latest = None
        
        res.append(ReferenceStatus(
            path=path,
            used=publish,
            latest=latest,
            is_latest=publish is latest if publish else False,
            all=siblings,
        ))
    
    return res

