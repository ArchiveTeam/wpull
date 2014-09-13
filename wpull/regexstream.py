'''Regular expression streams.'''


class RegexStream(object):
    '''Streams file with regular expressions.

    Args:
        file: File object.
        pattern: A compiled regular expression object.
        read_size (int): The size of a chunk of text that is searched.
        overlap_size (int): The amount of overlap between chunks of text
            that is searched.
    '''

    def __init__(self, file, pattern, read_size=16384, overlap_size=4096):
        self._file = file
        self._pattern = pattern
        self._read_size = read_size
        self._overlap_size = overlap_size

    def stream(self):
        '''Iterate the file stream.

        Returns:
            iterator: Each item is a tuple:

            1. None, regex match
            2. str
        '''
        chunk_a = None
        chunk_b = None
        chunk_a_index = 0
        chunk_b_index = 0
        search_start_index = 0

        while True:
            chunk_a = chunk_b
            chunk_a_index = chunk_b_index
            chunk_b = self._file.read(self._read_size)

            if chunk_a is None:
                continue

            chunk_b_index = chunk_a_index + len(chunk_a)

            if not chunk_a:
                break

            current_chunk = chunk_a + chunk_b[:self._overlap_size]

            offset_end = len(chunk_a) + self._overlap_size

            while True:
                offset_start = search_start_index - chunk_a_index
                match = self._pattern.search(
                    current_chunk, offset_start, offset_end)

                if not match:
                    unmatched_part = chunk_a[offset_start:]

                    if unmatched_part:
                        yield (None, unmatched_part)

                    search_start_index += len(unmatched_part)
                    break

                start_index, end_index = match.span(match.lastindex)

                unmatched_part = current_chunk[offset_start:start_index]

                if unmatched_part:
                    yield (None, unmatched_part)

                yield (match, match.group(match.lastindex))

                search_start_index += len(unmatched_part) + \
                    len(match.group(match.lastindex))
