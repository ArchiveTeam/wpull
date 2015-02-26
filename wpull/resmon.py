'''Resource monitor.'''
import collections
import gettext
import logging


_logger = logging.getLogger(__name__)
_ = gettext.gettext


try:
    import psutil
except ImportError:
    _logger.warning('psutil is not available.', exc_info=1)
    psutil = None


ResourceInfo = collections.namedtuple(
    'ResourceInfoType',
    ['path', 'free', 'limit']
)
'''Resource level information

Attributes:
    path (str, None): File path of the resource. ``None`` is provided for
        memory usage.
    free (int): Number of bytes available.
    limit (int): Minimum bytes of the resource.
'''


class ResourceMonitor(object):
    '''Monitor available resources such as disk space and memory.

    Args:
        resource_paths (list): List of paths to monitor. Recommended paths
            include temporary directories and the current working directory.
        min_disk (int, optional): Minimum disk space in bytes.
        min_memory (int, optional): Minimum memory in bytes.
    '''
    def __init__(self, resource_paths=('/',), min_disk=10000,
                 min_memory=10000):
        assert not isinstance(resource_paths, str), type(resource_paths)

        self._resource_paths = resource_paths
        self._min_disk = min_disk
        self._min_memory = min_memory

        if not psutil:
            raise OSError('psutil is not available')

    def get_info(self):
        '''Return ResourceInfo instances.'''
        if self._min_disk:
            for path in self._resource_paths:
                usage = psutil.disk_usage(path)

                yield ResourceInfo(path, usage.free, self._min_disk)

        if self._min_memory:
            usage = psutil.virtual_memory()

            yield ResourceInfo(None, usage.available, self._min_memory)

    def check(self):
        '''Check resource levels.

         Returns:
            None, ResourceInfo: If None is provided, no levels are exceeded.
                Otherwise, the first ResourceInfo exceeding limits is returned.
        '''

        for info in self.get_info():
            if info.free < info.limit:
                return info
