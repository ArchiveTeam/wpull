import gettext
import logging
import asyncio
import os
import ssl
import tempfile

import atexit

from wpull.backport.logging import BraceMessage as __
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession
import wpull.util

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class SSLContextTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        session.ssl_context = self._build_ssl_context(session)

    @classmethod
    def _build_ssl_context(cls, session: AppSession) -> ssl.SSLContext:
        '''Create the SSL options.

        The options must be accepted by the `ssl` module.
        '''
        args = session.args

        # Logic is based on tornado.netutil.ssl_options_to_context
        ssl_context = ssl.SSLContext(args.secure_protocol)

        if args.check_certificate:
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            cls._load_ca_certs(session)
            ssl_context.load_verify_locations(session.ca_certs_filename)
        else:
            ssl_context.verify_mode = ssl.CERT_NONE

        if args.strong_crypto:
            ssl_context.options |= ssl.OP_NO_SSLv2
            ssl_context.options |= ssl.OP_NO_SSLv3  # POODLE

            if hasattr(ssl, 'OP_NO_COMPRESSION'):
                ssl_context.options |= ssl.OP_NO_COMPRESSION  # CRIME
            else:
                _logger.warning(_('Unable to disable TLS compression.'))

        if args.certificate:
            ssl_context.load_cert_chain(args.certificate, args.private_key)

        if args.edg_file:
            ssl.RAND_egd(args.edg_file)

        if args.random_file:
            with open(args.random_file, 'rb') as in_file:
                # Use 16KB because Wget
                ssl.RAND_add(in_file.read(15360), 0.0)

        return ssl_context

    @classmethod
    def _load_ca_certs(cls, session: AppSession, clean: bool=True):
        '''Load the Certificate Authority certificates.
        '''
        args = session.args

        if session.ca_certs_filename:
            return session.ca_certs_filename

        certs = set()

        if args.use_internal_ca_certs:
            pem_filename = os.path.join(
                os.path.dirname(__file__), '..', '..', 'cert', 'ca-bundle.pem'
            )
            certs.update(cls._read_pem_file(pem_filename, from_package=True))

        if args.ca_directory:
            if os.path.isdir(args.ca_directory):
                for filename in os.listdir(args.ca_directory):
                    if os.path.isfile(filename):
                        certs.update(cls._read_pem_file(filename))
            else:
                _logger.warning(__(
                    _('Certificate directory {path} does not exist.'),
                    path=args.ca_directory
                ))

        if args.ca_certificate:
            if os.path.isfile(args.ca_certificate):
                certs.update(cls._read_pem_file(args.ca_certificate))
            else:
                _logger.warning(__(
                    _('Certificate file {path} does not exist.'),
                    path=args.ca_certificate
                ))

        session.ca_certs_filename = certs_filename = tempfile.mkstemp(
            suffix='.pem', prefix='tmp-wpull-')[1]

        def clean_certs_file():
            os.remove(certs_filename)

        if clean:
            atexit.register(clean_certs_file)

        with open(certs_filename, 'w+b') as certs_file:
            for cert in certs:
                certs_file.write(cert)

        _logger.debug('CA certs loaded.')

    @classmethod
    def _read_pem_file(cls, filename, from_package=False):
        '''Read the PEM file.

        Returns:
            iterable: An iterable of certificates. The certificate data
            is :class:`byte`.
        '''
        _logger.debug('Reading PEM {0}.'.format(filename))

        if from_package:
            return wpull.util.filter_pem(wpull.util.get_package_data(filename))

        with open(filename, 'rb') as in_file:
            return wpull.util.filter_pem(in_file.read())
