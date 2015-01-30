# encoding=utf-8
'''Python and Lua scripting support.'''
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.item import Status
from wpull.url import parse_url_or_log


_logger = logging.getLogger(__name__)


class HookDisconnected(Exception):
    '''No callback is connected.'''


class HookAlreadyConnectedError(Exception):
    '''A callback is already connected to the hook.'''


class HookableMixin(object):
    '''Dynamic callback hook system.'''
    def __init__(self):
        super().__init__()
        self.callback_hooks = {}

    def register_hook(self, *names):
        '''Register hooks that can be connected.'''
        for name in names:
            if name not in self.callback_hooks:
                self.callback_hooks[name] = None

    def unregister_hook(self, *names):
        '''Unregister hook.'''
        for name in names:
            del self.callback_hooks[name]

    def connect_hook(self, name, callback):
        '''Add callback to hook.'''
        if not self.callback_hooks[name]:
            self.callback_hooks[name] = callback
        else:
            raise HookAlreadyConnectedError('Callback hook already connected.')

    def disconnect_hook(self, name):
        '''Remove callback from hook.'''
        self.callback_hooks[name] = None

    def call_hook(self, name, *args, **kwargs):
        '''Invoke the callback.'''
        if self.callback_hooks[name]:
            return self.callback_hooks[name](*args, **kwargs)
        else:
            raise HookDisconnected('No callback is connected.')

    def is_hook_connected(self, name):
        '''Return whether the hook is connected.'''
        return bool(self.callback_hooks[name])


class HookStop(Exception):
    '''Stop the engine.'''
    pass


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


class LegacyCallbacks(object):
    '''Legacy callback hooks.

    API scripting versions were introduced when function signatures needed to
    be changed. Instead of breaking existing scripts in production, the
    default signature remained the same unless it was changed by the script.

    .. note:: Legacy functions are suffixed with an integer here only for
       documentation purposes. Do not include the integer suffix in your
       scripts; the argument signature will be adjusted automatically.

    Currently, no deprecated functions exist.
    '''


class Callbacks(LegacyCallbacks):
    '''Callback hooking instance.

    Attributes:
        AVAILABLE_VERSIONS (tuple): The available API versions.
        version (int): The current API version in use. You can set this.
            Default: 2.

    '''
    AVAILABLE_VERSIONS = (2,)

    def __init__(self):
        self._version = 2

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, num):
        assert num in self.AVAILABLE_VERSIONS, 'Unknown ver {}'.format(num)

        self._version = num

    @staticmethod
    def engine_run():
        '''Called when the Engine is about run.'''
        pass

    @staticmethod
    def resolve_dns(host):
        '''Resolve the hostname to an IP address.

        Args:
            host (str): The hostname.

        This callback is to override the DNS lookup.

        It is useful when the server is no longer available to the public.
        Typically, large infrastructures will change the DNS settings to
        make clients no longer hit the front-ends, but rather go towards
        a static HTTP server with a "We've been acqui-hired!" page. In these
        cases, the original servers may still be online.

        Returns:
            str, None: ``None`` to use the original behavior or a string
            containing an IP address or an alternate hostname.
        '''
        return None

    @staticmethod
    def accept_url(url_info, record_info, verdict, reasons):
        '''Return whether to download this URL.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            record_info (dict): A mapping containing the same information in
                :class:`.item.URLRecord`.
            verdict (bool): A bool indicating whether Wpull wants to download
                the URL.
            reasons (dict): A dict containing information for the verdict:

                * ``filters`` (dict): A mapping (str to bool) from filter name
                  to whether the filter passed or not.
                * ``reason`` (str): A short reason string. Current values are:
                  ``filters``, ``robots``, ``redirect``.

        Returns:
            bool: If ``True``, the URL should be downloaded. Otherwise, the URL
            is skipped.
        '''
        return verdict

    @staticmethod
    def queued_url(url_info):
        '''Callback fired after an URL was put into the queue.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
        '''

    @staticmethod
    def dequeued_url(url_info, record_info):
        '''Callback fired after an URL was retrieved from the queue.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            record_info (dict): A mapping containing the same information in
                :class:`.item.URLRecord`.
        '''

    @staticmethod
    def handle_pre_response(url_info, url_record, response_info):
        '''Return an action to handle a response status before a download.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            record_info (dict): A mapping containing the same information in
                :class:`.item.URLRecord`.
            response_info (dict): A mapping containing the same information
                in :class:`.http.request.Response` or
                :class:`.ftp.request.Response`.

        Returns:
            str: A value from :class:`Actions`. The default is
            :attr:`Actions.NORMAL`.
        '''
        return Actions.NORMAL

    @staticmethod
    def handle_response(url_info, record_info, response_info):
        '''Return an action to handle the response.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            record_info (dict): A mapping containing the same information in
                :class:`.item.URLRecord`.

                .. versionadded:: Scripting-API-2

            response_info (dict): A mapping containing the same information
                in :class:`.http.request.Response` or
                :class:`.ftp.request.Response`.

        Returns:
            str: A value from :class:`Actions`. The default is
            :attr:`Actions.NORMAL`.
        '''
        return Actions.NORMAL

    @staticmethod
    def handle_error(url_info, record_info, error_info):
        '''Return an action to handle the error.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            record_info (dict): A mapping containing the same information in
                :class:`.item.URLRecord`.

                .. versionadded:: Scripting-API-2

            error_info (dict): A mapping containing the keys:

                * ``error``: The name of the exception (for example,
                  ``ProtocolError``)

        Returns:
            str: A value from :class:`Actions`. The default is
            :attr:`Actions.NORMAL`.
        '''
        return Actions.NORMAL

    @staticmethod
    def get_urls(filename, url_info, document_info):
        '''Return additional URLs to be added to the URL Table.

        Args:
            filename (str): A string containing the path to the document.
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            document_info (dict): A mapping containing the same information in
                :class:`.body.Body`.

        .. Note:: The URLs provided do not replace entries in the URL Table.
           If a URL already exists in the URL Table, it will be ignored
           as defined in :class:`.database.URLTable`. As well, the URLs
           added do not reset the item Status to ``todo``. To override
           this behavior, see ``replace`` as described below.

        Returns:
            list: A ``list`` of ``dict``. Each ``dict`` contains:

                * ``url``: a string of the URL
                * ``link_type`` (str, optional): A string defined in
                  :class:`.item.LinkType`.
                * ``inline`` (bool, optional): If True, the link is an
                  embedded HTML object.
                * ``post_data`` (str, optional): If provided, the
                  request will be a POST request with a
                  ``application/x-www-form-urlencoded`` content type.
                * ``replace`` (bool, optional): If True and if the URL already
                  exists in the URL Table, the entry is deleted and replaced
                  with a new one.
        '''
        return None

    @staticmethod
    def wait_time(seconds):
        '''Return the wait time between requests.

        Args:
            seconds (float): The original time in seconds.

        Returns:
            float: The time in seconds.
        '''
        return seconds

    @staticmethod
    def finishing_statistics(start_time, end_time, num_urls, bytes_downloaded):
        '''Callback containing final statistics.

        Args:
            start_time (float): timestamp when the engine started
            end_time (float): timestamp when the engine stopped
            num_urls (int): number of URLs downloaded
            bytes_downloaded (int): size of files downloaded in bytes
        '''
        pass

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

        self.factory['Resolver'].connect_hook('resolve_dns', self._resolve_dns)
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

    def _resolve_dns(self, host, port):
        answer = self.callbacks.resolve_dns(host)

        _logger.debug(__('Resolve hook returned {0}', answer))

        if answer:
            return answer
        else:
            return host

    def _engine_run(self):
        self.callbacks.engine_run()

    def _exit_status(self, exit_status):
        return self.callbacks.exit_status(exit_status)

    def _finishing_statistics(self, start_time, stop_time, files, size):
        self.callbacks.finishing_statistics(
            start_time,
            stop_time,
            files,
            size
        )

    def _wait_time(self, seconds):
        return self.callbacks.wait_time(seconds)

    def _queued_url(self, url_info):
        url_info_dict = url_info.to_dict()

        self.callbacks.queued_url(url_info_dict)

    def _dequeued_url(self, url_info, url_record):
        url_info_dict = url_info.to_dict()
        record_info_dict = url_record.to_dict()

        self.callbacks.dequeued_url(url_info_dict, record_info_dict)

    def _should_fetch(self, url_info, url_record, verdict, reason_slug,
                      test_info):
        url_info_dict = url_info.to_dict()

        record_info_dict = url_record.to_dict()

        reasons = {
            'filters': test_info['map'],
            'reason': reason_slug,
        }

        verdict = self.callbacks.accept_url(
            url_info_dict, record_info_dict, verdict, reasons)

        _logger.debug('Hooked should fetch returned %s', verdict)

        return verdict

    def _handle_pre_response(self, request, response, url_record):
        url_info_dict = request.url_info.to_dict()
        url_record_dict = url_record.to_dict()

        response_info_dict = response.to_dict()
        action = self.callbacks.handle_pre_response(
            url_info_dict, url_record_dict, response_info_dict
        )

        _logger.debug(__('Hooked pre response returned {0}', action))

        return action

    def _handle_response(self, request, response, url_record):
        url_info_dict = request.url_info.to_dict()
        url_record_dict = url_record.to_dict()

        response_info_dict = response.to_dict()
        action = self.callbacks.handle_response(
            url_info_dict, url_record_dict, response_info_dict
        )

        _logger.debug(__('Hooked response returned {0}', action))

        return action

    def _handle_error(self, request, url_record, error):
        url_info_dict = request.url_info.to_dict()
        url_record_dict = url_record.to_dict()
        error_info_dict = {
            'error': error.__class__.__name__,
        }
        action = self.callbacks.handle_error(
            url_info_dict, url_record_dict, error_info_dict
        )

        _logger.debug(__('Hooked error returned {0}', action))

        return action

    def _scrape_document(self, request, response, url_item):
        url_info_dict = request.url_info.to_dict()
        document_info_dict = response.body.to_dict()
        filename = response.body.name

        new_url_dicts = self.callbacks.get_urls(
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


class PluginEnvironment(object):
    '''Plugin environment for customizing classes.

    Attributes:
        factory (:class:`.factory.Factory`): The factory ready to be modified.
        builder (:class:`.builder.Builder`): Application builder.
        plugin_args (str): Additional arguments for the plugin.
    '''
    def __init__(self, factory, builder, plugin_args):
        self.factory = factory
        self.builder = builder
        self.plugin_args = plugin_args
