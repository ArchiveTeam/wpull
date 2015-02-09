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
        restart_value (int): Optional value for ``REST`` command.
    '''
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.address = None
        self.data_address = None
        self.username = None
        self.password = None
        self.restart_value = None

    def to_dict(self):
        return {
            'protocol': 'ftp',
            'url': self.url,
            'url_info': self.url_info.to_dict() if self.url_info else None,
            'username': self.username,
            'password': self.password,
            'restart_value': self.restart_value,
        }

    def set_continue(self, offset):
        '''Modify the request into a restart request.'''
        assert offset >= 0, offset
        self.restart_value = offset


class Response(DictableMixin, ProtocolResponseMixin):
    '''FTP response for a file.

    Attributes:
        request (:class:`Request`): The corresponding request.
        body (:class:`.body.Body` or a file-like): The file.
        reply (:class:`Reply`): The latest Reply.
        file_transfer_size (int): Size of the file transfer without
            considering restart. (REST is issued last.)

            This is will be the file size. (STREAM mode is always used.)

        restart_value (int): Offset value of restarted transfer.
    '''
    def __init__(self):
        self.request = None
        self.body = None
        self.reply = None
        self.data_address = None
        self.file_transfer_size = None
        self.restart_value = None

    @property
    def protocol(self):
        return 'ftp'

    def to_dict(self):
        return {
            'protocol': 'ftp',
            'request': self.request.to_dict() if self.request else None,
            'body': self.call_to_dict_or_none(self.body),
            'reply': self.reply.to_dict() if self.reply else None,
            'response_code': self.reply.code if self.reply else None,
            'response_message': self.reply.text if self.reply else None,
            'file_transfer_size': self.file_transfer_size,
            'restart_value': self.restart_value,
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
