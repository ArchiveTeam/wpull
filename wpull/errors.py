# encoding=utf-8
'''Exceptions.'''


class ServerError(ValueError):
    '''Server issued an error.'''
    pass


class ProtocolError(ValueError):
    '''A protocol was not followed.'''
    pass


class SSLVerficationError(OSError):
    '''A problem occured validing SSL certificates.'''
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


class ExitStatus(object):
    '''Program exit status codes.'''
    generic_error = 1
    parser_error = 2
    file_io_error = 3
    network_failure = 4
    ssl_verification_error = 5
    authentication_failure = 6
    protocol_error = 7
    server_error = 8
