# encoding=utf-8
'''Python and Lua scripting support.

See :ref:`scripting-hooks` for an introduction.
'''
import enum
import functools
import logging

import asyncio

from wpull.application.plugin import WpullPlugin, PluginFunctionCategory
from wpull.backport.logging import BraceMessage as __

_logger = logging.getLogger(__name__)


class HookDisconnected(RuntimeError):
    '''No callback is connected.'''


class HookAlreadyConnectedError(ValueError):
    '''A callback is already connected to the hook.'''


class HookDispatcher(object):
    '''Dynamic callback hook system.'''
    def __init__(self):
        super().__init__()
        self._callbacks = {}

    def register(self, name: str):
        '''Register hooks that can be connected.'''
        if name in self._callbacks:
            raise ValueError('Hook already registered')

        self._callbacks[name] = None

    def unregister(self, name: str):
        '''Unregister hook.'''
        del self._callbacks[name]

    def connect(self, name, callback):
        '''Add callback to hook.'''
        if not self._callbacks[name]:
            self._callbacks[name] = callback
        else:
            raise HookAlreadyConnectedError('Callback hook already connected.')

    def disconnect(self, name: str):
        '''Remove callback from hook.'''
        self._callbacks[name] = None

    def call(self, name: str, *args, **kwargs):
        '''Invoke the callback.'''
        if self._callbacks[name]:
            return self._callbacks[name](*args, **kwargs)
        else:
            raise HookDisconnected('No callback is connected.')

    @asyncio.coroutine
    def call_async(self, name: str, *args, **kwargs):
        '''Invoke the callback.'''
        if self._callbacks[name]:
            return (yield from self._callbacks[name](*args, **kwargs))
        else:
            raise HookDisconnected('No callback is connected.')

    def is_connected(self, name: str) -> bool:
        '''Return whether the hook is connected.'''
        return bool(self._callbacks[name])

    def is_registered(self, name: str) -> bool:
        return name in self._callbacks


class EventDispatcher(object):
    def __init__(self):
        self._callbacks = {}

    def register(self, name: str):
        if name in self._callbacks:
            raise ValueError('Event already registered')

        self._callbacks[name] = set()

    def unregister(self, name: str):
        del self._callbacks[name]

    def add_listener(self, name: str, callback):
        self._callbacks[name].add(callback)

    def remove_listener(self, name: str, callback):
        self._callbacks[name].remove(callback)

    def notify(self, name: str, *args, **kwargs):
        for callback in self._callbacks[name]:
            callback(*args, **kwargs)

    def is_registered(self, name: str) -> bool:
        return name in self._callbacks


class HookableMixin(object):
    def __init__(self):
        super().__init__()
        self.hook_dispatcher = HookDispatcher()
        self.event_dispatcher = EventDispatcher()

    def connect_plugin(self, plugin: WpullPlugin):
        for func, name, category in plugin.get_plugin_functions():
            if category == PluginFunctionCategory.hook and self.hook_dispatcher.is_registered(name):
                _logger.debug('Connected hook %s %s', name, func)
                self.hook_dispatcher.connect(name, func)
            elif category == PluginFunctionCategory.event and self.event_dispatcher.is_registered(name):
                _logger.debug('Connected event %s %s', name, func)
                self.event_dispatcher.add_listener(name, func)


class HookStop(Exception):
    '''Stop the engine.

    Raise this exception as a more graceful alternative to ``sys.exit()``.
    '''


class Actions(enum.Enum):
    '''Actions for handling responses and errors.

    Attributes:
        NORMAL (normal): Use Wpull's original behavior.
        RETRY (retry): Retry this item (as if an error has occurred).
        FINISH (finish): Consider this item as done; don't do any further
            processing on it.
        STOP (stop): Raises :class:`HookStop` to stop the Engine from running.
    '''
    NORMAL = 'normal'
    RETRY = 'retry'
    FINISH = 'finish'
    STOP = 'stop'
