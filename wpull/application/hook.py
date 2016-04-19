# encoding=utf-8
'''Python and Lua scripting support.

See :ref:`scripting-hooks` for an introduction.
'''
import functools
import logging

import asyncio

from wpull.backport.logging import BraceMessage as __
from wpull.url import parse_url_or_log

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


class HookStop(Exception):
    '''Stop the engine.

    Raise this exception as a more graceful alternative to ``sys.exit()``.
    '''


class Actions(object):
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


class Callbacks(object):
    '''Callback hooking instance.

    Attributes:
        AVAILABLE_VERSIONS (tuple): The available API versions as integers.
        version (int): The current API version in use. You can set this.
            Default: 2.

    An instance of this class is available in the hook environment. You
    set your functions to the instance to override the default functions.

    All functions are called with builtin Python types. i.e., complex objects
    are converted to ``dict`` using the instance's ``to_dict`` method. Be
    careful of values being None.

    API scripting versions were introduced when function signatures needed to
    be changed. Instead of breaking existing scripts in production, the
    default signature remained the same unless it was changed by the script.
    '''
    AVAILABLE_VERSIONS = (2, 3)

    def __init__(self):
        self._version = 2

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, num):
        assert num in self.AVAILABLE_VERSIONS, 'Unknown ver {}'.format(num)

        self._version = num

    def dispatch_engine_run(self):
        '''Call appropriate ``engine_run``.'''
        func = getattr(self, 'engine_run', CallbacksV2.engine_run)
        return func()

    def dispatch_resolve_dns(self, host):
        '''Call appropriate ``resolve_dns``.'''
        func = getattr(self, 'resolve_dns', CallbacksV2.resolve_dns)
        return func(host)

    def dispatch_accept_url(self, url_info, record_info, verdict, reasons):
        '''Call appropriate ``accept_url``.'''
        func = getattr(self, 'accept_url', CallbacksV2.accept_url)
        return func(url_info, record_info, verdict, reasons)

    def dispatch_queued_url(self, url_info):
        '''Call appropriate ``queued_url``.'''
        func = getattr(self, 'queued_url', CallbacksV2.queued_url)
        return func(url_info)

    def dispatch_dequeued_url(self, url_info, record_info):
        '''Call appropriate ``dequeued_url``.'''
        func = getattr(self, 'dequeued_url', CallbacksV2.dequeued_url)
        return func(url_info, record_info)

    def dispatch_handle_pre_response(self, url_info, url_record, response_info):
        '''Call appropriate ``handle_pre_response``.'''
        func = getattr(self, 'handle_pre_response', CallbacksV2.handle_pre_response)
        return func(url_info, url_record, response_info)

    def dispatch_handle_response(self, url_info, record_info, response_info):
        '''Call appropriate ``handle_response``.'''
        func = getattr(self, 'handle_response', CallbacksV2.handle_response)
        return func(url_info, record_info, response_info)

    def dispatch_handle_error(self, url_info, record_info, error_info):
        '''Call appropriate ``handle_error``.'''
        func = getattr(self, 'handle_error', CallbacksV2.handle_error)
        return func(url_info, record_info, error_info)

    def dispatch_get_urls(self, filename, url_info, document_info):
        '''Call appropriate ``get_urls``.'''
        func = getattr(self, 'get_urls', CallbacksV2.get_urls)
        return func(filename, url_info, document_info)

    def dispatch_wait_time(self, seconds, url_info_dict, record_info_dict,
                           response_info_dict, error_info_dict):
        '''Call appropriate ``wait_time``.'''

        if self._version == 2:
            func = functools.partial(
                getattr(self, 'wait_time', CallbacksV2.wait_time),
                seconds
            )
        else:
            func = functools.partial(
                getattr(self, 'wait_time', CallbacksV3.wait_time),
                seconds, url_info_dict, record_info_dict,
                response_info_dict, error_info_dict
            )

        return func()

    def dispatch_finishing_statistics(self, start_time, end_time, num_urls, bytes_downloaded):
        '''Call appropriate ``finishing_statistics``.'''
        func = getattr(self, 'finishing_statistics', CallbacksV2.finishing_statistics)
        return func(start_time, end_time, num_urls, bytes_downloaded)

    def dispatch_exit_status(self, exit_code):
        '''Call appropriate ``exit_status``.'''
        func = getattr(self, 'exit_status', CallbacksV2.exit_status)
        return func(exit_code)


class CallbacksV2(Callbacks):
    '''Callbacks API Version 2.'''

    @staticmethod
    def engine_run():
        '''Called when the Engine is about run.'''



    @staticmethod
    def finishing_statistics(start_time, end_time, num_urls, bytes_downloaded):
        '''Callback containing final statistics.

        Args:
            start_time (float): timestamp when the engine started
            end_time (float): timestamp when the engine stopped
            num_urls (int): number of URLs downloaded
            bytes_downloaded (int): size of files downloaded in bytes
        '''

    @staticmethod
    def exit_status(exit_code):
        '''Return the program exit status code.

        Exit codes are values from :class:`errors.ExitStatus`.

        Args:
            exit_code (int): The exit code Wpull wants to return.

        Returns:
            int: The exit code that Wpull will return.
        '''
        return exit_code


class CallbacksV3(CallbacksV2):
    '''Callbacks API Version 3.

    .. versionadded:: 0.1009a1
    '''


class HookEnvironment(object):
    '''The global instance used by scripts.

    Attributes:
        factory (:class:`.factory.Factory`): The factory with the instances
            built for the application.
        is_lua (bool): Whether the script is running as Lua.
        actions (:class:`Actions`): The Actions instance.
        callbacks (:class:`Callbacks`): The Callback instance.
    '''
    def __init__(self, factory):
        self.factory = factory
        self.actions = Actions()
        self.callbacks = Callbacks()

    def connect_hooks(self):
        '''Connect callbacks to hooks.'''

        self.factory['Engine'].connect_hook('engine_run', self._engine_run)
        self.factory['URLTable'].connect_hook(
            'dequeued_url',
            self._dequeued_url)
        self.factory['Application'].connect_hook(
            'exit_status', self._exit_status
        )
        self.factory['Application'].connect_hook(
            'finishing_statistics', self._finishing_statistics
        )
        self.factory['ResultRule'].connect_hook('wait_time', self._wait_time)
        self.factory['URLTable'].connect_hook(
            'queued_url',
            self._queued_url)
        self.factory['FetchRule'].connect_hook(
            'should_fetch',
            self._should_fetch)
        self.factory['ResultRule'].connect_hook(
            'handle_pre_response',
            self._handle_pre_response)
        self.factory['ResultRule'].connect_hook(
            'handle_response',
            self._handle_response)
        self.factory['ResultRule'].connect_hook(
            'handle_error',
            self._handle_error)
        self.factory['ProcessingRule'].connect_hook(
            'scrape_document',
            self._scrape_document)

    def _engine_run(self):
        '''Process engine run callback.'''
        self.callbacks.dispatch_engine_run()

    def _exit_status(self, exit_status):
        '''Process exit status callback.'''
        return self.callbacks.dispatch_exit_status(exit_status)

    def _finishing_statistics(self, start_time, stop_time, files, size):
        '''Process finishing statistics callback.'''
        self.callbacks.dispatch_finishing_statistics(
            start_time,
            stop_time,
            files,
            size
        )

    def _wait_time(self, seconds, request, url_record, response, error):
        '''Process wait time callback.'''
        url_info_dict = request.url_info.to_dict()
        record_info_dict = url_record.to_dict()

        if response:
            response_info_dict = response.to_dict()
        else:
            response_info_dict = None

        if error:
            error_info_dict = {
                'error': error.__class__.__name__,
            }
        else:
            error_info_dict = None

        return self.callbacks.dispatch_wait_time(
            seconds, url_info_dict, record_info_dict, response_info_dict,
            error_info_dict
        )

    def _should_fetch(self, url_info, url_record, verdict, reason_slug,
                      test_info):
        '''Process should fetch callback.'''
        url_info_dict = url_info.to_dict()

        record_info_dict = url_record.to_dict()

        reasons = {
            'filters': test_info['map'],
            'reason': reason_slug,
        }

        verdict = self.callbacks.dispatch_accept_url(
            url_info_dict, record_info_dict, verdict, reasons)

        _logger.debug('Hooked should fetch returned %s', verdict)

        return verdict

    def _handle_pre_response(self, request, response, url_record):
        '''Process pre-response callback.'''
        url_info_dict = request.url_info.to_dict()
        url_record_dict = url_record.to_dict()

        response_info_dict = response.to_dict()
        action = self.callbacks.dispatch_handle_pre_response(
            url_info_dict, url_record_dict, response_info_dict
        )

        _logger.debug(__('Hooked pre response returned {0}', action))

        return action

    def _handle_response(self, request, response, url_record):
        '''Process response callback.'''
        url_info_dict = request.url_info.to_dict()
        url_record_dict = url_record.to_dict()

        response_info_dict = response.to_dict()
        action = self.callbacks.dispatch_handle_response(
            url_info_dict, url_record_dict, response_info_dict
        )

        _logger.debug(__('Hooked response returned {0}', action))

        return action

    def _handle_error(self, request, url_record, error):
        '''Process error callback.'''
        url_info_dict = request.url_info.to_dict()
        url_record_dict = url_record.to_dict()
        error_info_dict = {
            'error': error.__class__.__name__,
        }
        action = self.callbacks.dispatch_handle_error(
            url_info_dict, url_record_dict, error_info_dict
        )

        _logger.debug(__('Hooked error returned {0}', action))

        return action

    def _scrape_document(self, request, response, url_item):
        '''Process scraping document callback.'''
        url_info_dict = request.url_info.to_dict()
        document_info_dict = response.body.to_dict()
        filename = response.body.name

        new_url_dicts = self.callbacks.dispatch_get_urls(
            filename, url_info_dict, document_info_dict)

        _logger.debug(__('Hooked scrape returned {0}', new_url_dicts))

        if not new_url_dicts:
            return

        for new_url_dict in new_url_dicts:
            self._add_hooked_url(url_item, new_url_dict)

    def _add_hooked_url(self, url_item, new_url_dict):
        '''Process the ``dict`` from the script and add the URLs.'''
        url = new_url_dict['url']
        link_type = new_url_dict.get('link_type')
        inline = new_url_dict.get('inline')
        post_data = new_url_dict.get('post_data')
        replace = new_url_dict.get('replace')

        assert url

        url_info = parse_url_or_log(url)

        if not url_info:
            return

        kwargs = dict(link_type=link_type, post_data=post_data)

        if replace:
            url_item.url_table.remove_one(url)

        url_item.add_child_url(url_info.url, inline=inline, **kwargs)


def callback_decorator(name: str, category: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.callback_name = name
        wrapper.callback_category = category

        return wrapper
    return decorator


def hook_function(name: str):
    return functools.partial(callback_decorator, category='hook')


def event_function(name: str):
    return functools.partial(callback_decorator, category='event')
