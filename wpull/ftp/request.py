'''FTP conversation classes'''
import re

from wpull.abstract.request import SerializableMixin, DictableMixin, \
    URLPropertyMixin, ProtocolResponseMixin
from wpull.errors import ProtocolError
import wpull.ftp.util


class Command(SerializableMixin, DictableMixin):
    '''FTP request command.

    Encoding is Latin-1.

    Attributes:
        name (str): The command. Usually 4 characters or less.
        argument (str): Optional argument for the command.
    '''
    def __init__(self, name=None, argument=''):
        self._name = None

        if name:
            self.name = name

        self.argument = argument

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value.upper()

    def parse(self, data):
        assert self.name is None
        assert not self.argument

        match = re.match(br'(\w+) ?([^\r\n]*)', data)

        if not match:
            raise ProtocolError('Failed to parse command.')

        self.name = match.group(1).decode('latin-1')
        self.argument = match.group(2).decode('latin-1')

    def to_bytes(self):
        return '{0} {1}\r\n'.format(self.name, self.argument).encode('latin-1')

    def to_dict(self):
        return {
            'name': self.name,
            'argument': self.argument,
        }


class Reply(SerializableMixin, DictableMixin):
    '''FTP reply.

    Encoding is always Latin-1.

    Attributes:
        code (int): Reply code.
        text (str): Reply message.
    '''
    def __init__(self, code=None, text=None):
        self.code = code
        self.text = text

    def parse(self, data):
        for line in data.splitlines(False):
            match = re.match(br'(\d{3}|^)([ -]?)(.*)', line)

            if not match:
                raise ProtocolError('Failed to parse reply.')

            if match.group(1) and match.group(2) == b' ':
                assert self.code is None
                self.code = int(match.group(1))

            if self.text is None:
                self.text = match.group(3).decode('latin-1')
            else:
                self.text += '\r\n{0}'.format(match.group(3).decode('latin-1'))

    def to_bytes(self):
        assert self.code is not None
        assert self.text is not None

        text_lines = self.text.splitlines(False)
        lines = []

        for row_num in range(len(text_lines)):
            line = text_lines[row_num]

            if row_num == len(text_lines) - 1:
                lines.append('{0} {1}\r\n'.format(self.code, line))
            else:
                lines.append('{0}-{1}\r\n'.format(self.code, line))

        return ''.join(lines).encode('latin-1')

    def to_dict(self):
        return {
            'code': self.code,
            'text': self.text
        }

    def code_tuple(self):
        '''Return a tuple of the reply code.'''
        return wpull.ftp.util.reply_code_tuple(self.code)


class Request(URLPropertyMixin):
    '''FTP request for a file.

    Attributes:
        address (tuple): Address of control connection.
        data_address (tuple): Address of data connection.
        username (str): Username for login.
        password (str): Password for login.
    '''
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.address = None
        self.data_address = None
        self.username = None
        self.password = None

    def to_dict(self):
        return {
            'protocol': 'ftp',
            'url': self.url,
            'url_info': self.url_info.to_dict() if self.url_info else None,
            'username': self.username,
            'password': self.password,
        }


class Response(DictableMixin, ProtocolResponseMixin):
    '''FTP response for a file.

    Attributes:
        request (:class:`Request`): The corresponding request.
        body (:class:`.body.Body`): The file.
        reply (:class:`Reply`): The latest Reply.
    '''
    def __init__(self):
        self.request = None
        self.body = None
        self.reply = None
        self.data_address = None

    def to_dict(self):
        return {
            'protocol': 'ftp',
            'request': self.request.to_dict(),
            'body': self.body.to_dict() if self.body else None,
            'reply': self.reply.to_dict(),
            'response_code': self.reply.code,
            'response_message': self.reply.text,
        }

    def response_code(self):
        return self.reply.code

    def response_message(self):
        return self.reply.text

    def __str__(self):
        return '{} {}\n'.format(
            self.reply.code,
            wpull.string.printable_str(self.reply.text, keep_newlines=True)
        )


class ListingResponse(Response):
    '''FTP response for a file listing.

    Attributes:
        files (list): A list of :class:`.ftp.ls.listing.FileEntry`
    '''
    def __init__(self):
        super().__init__()
        self.files = []

    def to_dict(self):
        dict_obj = super().to_dict()
        dict_obj['files'] = self.files
        return dict_obj
