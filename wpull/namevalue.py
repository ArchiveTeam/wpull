# encoding=utf-8
'''Key-value pairs.'''
import collections
import gettext
import io

from wpull.collections import OrderedDefaultDict


_ = gettext.gettext


class NameValueRecord(collections.MutableMapping):
    '''An ordered mapping of name-value pairs.

    Duplicated names are accepted.

    .. seealso:: http://tools.ietf.org/search/draft-kunze-anvl-02
    '''
    def __init__(self, normalize_overrides=None, encoding='utf-8'):
        self._map = OrderedDefaultDict(list)
        self.raw = None
        self.encoding = encoding
        self._normalize_overrides = normalize_overrides

    def parse(self, string, strict=True):
        '''Parse the string or bytes.

        Args:
            script: If True, errors will not be ignored

        Raises:
            :class:`ValueError` if the record is malformed.
        '''
        if isinstance(string, bytes):
            errors = 'strict' if strict else 'replace'
            string = string.decode(self.encoding, errors=errors)

        if not self.raw:
            self.raw = string
        else:
            self.raw += string

        line_ending = guess_line_ending(string)
        lines = unfold_lines(string).split(line_ending)
        for line in lines:
            if line:
                if ':' not in line:
                    if strict:
                        raise ValueError('Field missing colon.')
                    else:
                        continue

                name, value = line.split(':', 1)
                name = name.strip()
                value = value.strip()
                self.add(name, value)

    def __getitem__(self, name):
        normalized_name = normalize_name(name, self._normalize_overrides)

        if normalized_name in self._map:
            if self._map[normalized_name]:
                return self._map[normalized_name][0]

        raise KeyError(name)

    def __setitem__(self, name, value):
        normalized_name = normalize_name(name, self._normalize_overrides)
        self._map[normalized_name][:] = (value,)

    def __delitem__(self, name):
        del self._map[normalize_name(name, self._normalize_overrides)]

    def __iter__(self):
        return iter(self._map)

    def __len__(self):
        return len(self._map)

    def add(self, name, value):
        '''Append the name-value pair to the record.'''
        normalized_name = normalize_name(name, self._normalize_overrides)
        self._map[normalized_name].append(value)

    def get_list(self, name):
        '''Return all the values for given name.'''
        normalized_name = normalize_name(name, self._normalize_overrides)
        return self._map[normalized_name]

    def get_all(self):
        '''Return an iterator of name-value pairs.'''
        for name, values in self._map.items():
            for value in values:
                yield (name, value)

    def __str__(self):
        return self.to_str()

    def to_str(self):
        '''Convert to string.'''
        pairs = []
        for name, value in self.get_all():
            if value:
                pairs.append('{0}: {1}'.format(name, value))
            else:
                pairs.append('{0}:'.format(name))

        pairs.append('')
        return '\r\n'.join(pairs)

    def __bytes__(self):
        return self.to_bytes()

    def to_bytes(self, errors='strict'):
        '''Convert to bytes.'''
        return str(self).encode(self.encoding, errors=errors)


def normalize_name(name, overrides=None):
    '''Normalize the key name to title case.

    For example, ``normalize_name('content-id')`` will become ``Content-Id``

    Args:
        name (str): The name to normalize.
        overrides (set, sequence): A set or sequence containing keys that
            should be cased to themselves. For example, passing
            ``set('WARC-Type')`` will normalize any key named "warc-type" to
            ``WARC-Type`` instead of the default ``Warc-Type``.

    Returns:
        str
    '''

    normalized_name = name.title()

    if overrides:
        override_map = dict([(name.title(), name) for name in overrides])

        return override_map.get(normalized_name, normalized_name)
    else:
        return normalized_name


def guess_line_ending(string):
    '''Return the most likely line delimiter from the string.'''
    assert isinstance(string, str), 'Expect str. Got {}'.format(type(string))
    crlf_count = string.count('\r\n')
    lf_count = string.count('\n')

    if crlf_count >= lf_count:
        return '\r\n'
    else:
        return '\n'


def unfold_lines(string):
    '''Join lines that are wrapped.

    Any line that starts with a space or tab is joined to the previous
    line.
    '''
    assert isinstance(string, str), 'Expect str. Got {}'.format(type(string))
    line_ending = guess_line_ending(string)
    lines = string.split(line_ending)
    line_buffer = io.StringIO()

    for line_number in range(len(lines)):
        line = lines[line_number]
        if line and line[0:1] in (' ', '\t'):
            line_buffer.write(' ')
        elif line_number != 0:
            line_buffer.write(line_ending)
        line_buffer.write(line.strip())

    return line_buffer.getvalue()
