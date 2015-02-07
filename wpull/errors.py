# encoding=utf-8
'''Exceptions.'''


class ServerError(ValueError):
    '''Server issued an error.'''


class ProtocolError(ValueError):
    '''A protocol was not followed.'''


class SSLVerificationError(OSError):
    '''A problem occurred validating SSL certificates.'''


SSLVerficationError = SSLVerificationError


class NetworkError(OSError):
    '''A networking error.'''


class ConnectionRefused(NetworkError):
    '''Server was online, but nothing was being served.'''


class DNSNotFound(NetworkError):
    '''Server's IP address could not be located.'''


class NetworkTimedOut(NetworkError):
    '''Connection read/write timed out.'''


# TODO: use AuthenticationError


class ExitStatus(object):
    '''Program exit status codes.

    Attributes:
        generic_error (1): An unclassified serious or fatal error occurred.
        parser_error (2): A local document or configuration file could not
            be parsed.
        file_io_error (3): A problem with reading/writing a file occurred.
        network_failure (4): A problem with the network occurred such as a DNS
            resolver error or a connection was refused.
        ssl_verification_error (5): A server's SSL/TLS certificate was invalid.
        authentication_failure (6): A problem with a username or password.
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


ERROR_PRIORITIES = (
    ServerError,
    ProtocolError,
    SSLVerificationError,
    DNSNotFound,
    ConnectionRefused,
    NetworkError,
    OSError,
    IOError,
    ValueError,
)
'''List of error classes by least severe to most severe.'''
