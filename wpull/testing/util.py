import contextlib
import logging
import os
from tempfile import TemporaryDirectory

_logger = logging.getLogger(__name__)


class TempDirMixin:
    def set_up_temp_dir(self):
        assert not getattr(self, 'original_dir', None), self.original_dir
        self.original_dir = os.getcwd()
        self.temp_dir = TemporaryDirectory()
        os.chdir(self.temp_dir.name)

        _logger.debug('Switch to %s', self.temp_dir.name)

    def tear_down_temp_dir(self):
        os.chdir(self.original_dir)
        self.temp_dir.cleanup()
        self.original_dir = None

    @contextlib.contextmanager
    def cd_tempdir(self):
        original_dir = os.getcwd()

        with TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                yield temp_dir
            finally:
                os.chdir(original_dir)
