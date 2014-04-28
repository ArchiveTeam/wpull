# encoding=utf-8
'''FTP request and response.'''
import re

from wpull.conversation import BaseRequest, BaseResponse
from wpull.errors import ProtocolError
import wpull.string


class Request(BaseRequest):
    '''Represents an FTP command request.'''
    def __init__(self, method=None, resource_name=None,):
        super().__init__('FTP', method, resource_name)

    def parse(self, data):
        '''Parse.'''
        text, self.encoding = wpull.string.fallback_decode(data)
        match = re.match(r'(\w+) (.*)', text)

        if match:
            self.method = match.group(1)
            self.resource_name = match.group(2)
        else:
            raise ProtocolError('Error parsing command.')

    def to_str(self):
        '''Return the command as a string.'''
        if self.resource_name:
            return '{0} {1}\r\n'.format(self.method, self.resource_name)
        else:
            return '{0}\r\n'.format(self.method)

    def to_bytes(self):
        '''Return the command as bytes.'''
        return self.to_str().encode(self.encoding)


class Response(BaseResponse):
    '''Represents the FTP response.'''
    def __init__(self, status_code=None, status_reason=None):
        super().__init__('FTP', status_code, status_reason)

    def parse(self, data):
        '''Parse.'''
        text, self.encoding = wpull.string.fallback_decode(data)

        message_list = []
        continuation = None

        for line in text.split('\n'):
            match = re.match(r'([0-9]{3})([ -])(.*)', line)

            if match:
                self.status_code = int(match.group(1))
                continuation = match.group(2)
                message_list.append(match.group(3).strip())
            else:
                message_list.append(line.strip())

        return continuation != '-'

    def to_str(self):
        '''Return the message status line as a string.'''
        lines = list(self.status_reason.split('\n'))

        for index in range(len(lines)):
            if index == len(lines) - 1:
                lines[index] = '{0} {1}'.format(self.status_code, lines[index])
            else:
                lines[index] = '{0}-{1}'.format(self.status_code, lines[index])

        return '\r\n'.join(lines)

    def to_bytes(self):
        '''Return the message status line as bytes.'''
        return self.to_str().encode(self.encoding)
