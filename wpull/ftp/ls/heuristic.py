'''Heuristics.'''
import re


def guess_listing_type(text, threshold=100):
    '''Guess the style of directory listing.

    Returns:
        str: ``unix``, ``msdos``, ``nlst``, ``unknown``.
    '''
    scores = {
        'unix': 0,
        'msdos': 0,
        'nlst': 0,
    }
    lines = text.splitlines(False)

    for line in lines:
        if not line:
            continue

        if re.search(r'---|r--|rw-|rwx', text):
            scores['unix'] += 1

        if '<DIR>' in line:
            scores['msdos'] += 1

        words = line.split(' ', 1)

        if len(words) == 1:
            scores['nlst'] += 1

        if max(scores.values()) > threshold:
            break

    results = tuple(reversed(sorted(scores.items(), key=lambda item: item[1])))

    if results[0][1]:
        return results[0][0]
    else:
        return 'unknown'
