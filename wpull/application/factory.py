# encoding=utf-8
'''Instance creation and management.'''
import collections


class Factory(collections.Mapping, object):
    '''Allows selection of classes and keeps track of instances.

    This class behaves like a mapping. Keys are names of classes and values are
    instances.
    '''
    def __init__(self, class_map=None):
        super().__init__()
        self._class_map = class_map or {}
        self._instance_map = {}

    @property
    def class_map(self):
        '''A mapping of names to class types.'''
        return self._class_map

    @property
    def instance_map(self):
        '''A mapping of names to instances.'''
        return self._instance_map

    def set(self, name, class_):
        '''Set the callable or class to be used.

        Args:
            name (str): The name of the class.
            class_: The class or a callable factory function.
        '''
        self._class_map[name] = class_

    def __getitem__(self, key):
        return self._instance_map[key]

    def __iter__(self):
        return iter(self._instance_map)

    def __len__(self):
        return len(self._instance_map)

    def new(self, name, *args, **kwargs):
        '''Create an instance.

        Args:
            name (str): The name of the class
            args: The arguments to pass to the class.
            kwargs: The keyword arguments to pass to the class.

        Returns:
            instance
        '''
        if name in self._instance_map:
            raise ValueError('Instance {0} is already initialized'
                             .format(name))

        instance = self._class_map[name](*args, **kwargs)
        self._instance_map[name] = instance
        return instance

    def is_all_initialized(self):
        '''Return whether all the instances have been initialized.

        Returns:
            bool
        '''
        return frozenset(self._class_map.keys()) == \
            frozenset(self._instance_map.keys())
