'''Parsing using html5lib python.'''
import html5lib.constants
import html5lib.tokenizer
import io
import os.path

from wpull.collections import FrozenDict, EmptyFrozenDict
from wpull.document.htmlparse.base import BaseParser
from wpull.document.htmlparse.element import Comment, Doctype, Element


DOCTYPE = html5lib.constants.tokenTypes['Doctype']
CHARACTERS = html5lib.constants.tokenTypes['Characters']
SPACE_CHARACTERS = html5lib.constants.tokenTypes['SpaceCharacters']
START_TAG = html5lib.constants.tokenTypes['StartTag']
END_TAG = html5lib.constants.tokenTypes['EndTag']
EMPTY_TAG = html5lib.constants.tokenTypes['EmptyTag']
COMMENT = html5lib.constants.tokenTypes['Comment']
PARSE_ERROR = html5lib.constants.tokenTypes['ParseError']


class HTMLParser(BaseParser):
    @property
    def parser_error(self):
        return ValueError

    def parse(self, file, encoding=None):
        tokenizer = html5lib.tokenizer.HTMLTokenizer(
            file, encoding=encoding,
            useChardet=False if encoding else True,
            parseMeta=False if encoding else True,
        )

        tag = None
        attrib = None
        buffer = None
        tail_buffer = None

        for token in tokenizer:
            token_type = token['type']

            if token_type == START_TAG:
                if buffer:
                    yield Element(tag, attrib, buffer.getvalue(), None, False)
                    buffer = None

                if tail_buffer:
                    yield Element(tag, EmptyFrozenDict(), None, tail_buffer.getvalue(), True)
                    tail_buffer = None

                tag = token['name']
                attrib = FrozenDict(dict(token['data']))
                buffer = io.StringIO()

                if token['name'] == 'script':
                    tokenizer.state = tokenizer.scriptDataState

            elif token_type in (CHARACTERS, SPACE_CHARACTERS):
                if buffer:
                    buffer.write(token['data'])
                if tail_buffer:
                    tail_buffer.write(token['data'])

            elif token_type == END_TAG:
                if buffer:
                    yield Element(tag, attrib, buffer.getvalue(), None, False)
                    buffer = None

                if tail_buffer:
                    yield Element(tag, EmptyFrozenDict(), None, tail_buffer.getvalue(), True)
                    tail_buffer = None

                tail_buffer = io.StringIO()
                tag = token['name']

            elif token_type == COMMENT:
                yield Comment(token['data'])
            elif token_type == DOCTYPE:
                yield Doctype('{} {} {}'.format(
                    token['name'], token['publicId'], token['systemId']))
            elif token_type == PARSE_ERROR:
                pass
            else:
                raise ValueError('Unhandled token {}'.format(token))

        if buffer:
            yield Element(tag, attrib, buffer.getvalue(), None, False)
            buffer = None

        if tail_buffer:
            yield Element(tag, EmptyFrozenDict(), None, tail_buffer.getvalue(), True)
            tail_buffer = None


if __name__ == '__main__':
    path = os.path.join(
        os.path.dirname(__file__), '..', '..',
        'testing', 'samples', 'xkcd_1.html'
        )
    with open(path, 'rb') as in_file:
        tokenizer = html5lib.tokenizer.HTMLTokenizer(in_file)

        for token in tokenizer:
            print(token)
        html_parser = HTMLParser()
        for element in html_parser.parse(in_file):
            print(element)
