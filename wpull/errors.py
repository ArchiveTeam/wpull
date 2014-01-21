# encoding=utf-8


class ServerError(ValueError):
    pass


class ProtocolError(ValueError):
    pass


class SSLVerficationError(OSError):
    pass


class NetworkError(OSError):
    pass


class ConnectionRefused(NetworkError):
    pass


class DNSNotFound(NetworkError):
    pass


class ExitStatus(object):
    generic_error = 1
    parser_error = 2
    file_io_error = 3
    network_failure = 4
    ssl_verification_error = 5
    authentication_failure = 6
    protocol_error = 7
    server_error = 8
