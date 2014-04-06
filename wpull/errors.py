# encoding=utf-8
'''Exceptions.'''


class ServerError(ValueError):
    '''Server issued an error.'''
    pass


class ProtocolError(ValueError):
    '''A protocol was not followed.'''
    pass


class SSLVerficationError(OSError):
    '''A problem occurred validating SSL certificates.'''
    pass


class NetworkError(OSError):
    '''A networking error.'''
    pass


class ConnectionRefused(NetworkError):
    '''Server was online, but nothing was being served.'''
    pass


class DNSNotFound(NetworkError):
    '''Server's IP address could not be located.'''
    pass


class NetworkTimedOut(NetworkError):
    '''Connection read/write timed out.'''
    pass


class ExitStatus(object):
    '''Program exit status codes.

    Attributes:
        generic_error (1): A serious error occurred.
        parser_error (2): A document failed to parse.
        file_io_error (3): A problem with reading/writing a file occurred.
        network_failure (4): A problem with the network occurred such as a DNS
            resolver error or a connection was refused.
        ssl_verification_error (5): A server's SSL/TLS certificate was invalid.
        authentication_failure (7): A problem with a username or password.
        protocol_error (7): A problem with communicating with a server
            occurred.
        server_error (8): The server had problems fulfilling our requests.
    '''
    generic_error = 1
    parser_error = 2
    file_io_error = 3
    network_failure = 4
    ssl_verification_error = 5
    authentication_failure = 6
    protocol_error = 7
    server_error = 8
