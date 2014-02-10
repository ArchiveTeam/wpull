# encoding=utf-8
'''Python and Lua scripting supprt.'''
import contextlib
import itertools
import logging
import sys
import tornado.gen

from wpull.database import Status
from wpull.engine import Engine
from wpull.network import Resolver
from wpull.processor import WebProcessor, WebProcessorSession
import wpull.util


_logger = logging.getLogger(__name__)


def load_lua():
    '''Load the Lua module.

    :seealso: http://stackoverflow.com/a/8403467/1524507
    '''
    import DLFCN
    sys.setdlopenflags(DLFCN.RTLD_NOW | DLFCN.RTLD_GLOBAL)
    import lua
    return lua


try:
    lua = load_lua()
except ImportError:
    lua = None


class HookStop(Exception):
    '''Stop the engine.'''
    pass


class Actions(object):
    '''Actions for ``handle_error`` and ``handle_response``.'''
    NORMAL = 'normal'
    '''Use Wpull's original behavior.'''
    RETRY = 'retry'
    '''Retry this item (as if an error has occured).'''
    FINISH = 'finish'
    '''Consider this item as done; don't do any further processing on it.'''
    STOP = 'stop'
    '''Raises :class:`HookStop` to stop the Engine from running.'''


class Callbacks(object):
    '''Callback hooking instance.'''
    @staticmethod
    def resolve_dns(host):
        '''Resolve the hostname to an IP address.

        This callback is to override the DNS response.

        It is useful when the server is no longer available to the public.
        Typically, large infrastructures will change the DNS settings to
        make clients no longer hit the front-ends, but rather go towards
        a static HTTP server with a "We've been acqui-hired!" page. In these
        cases, the original servers may still be online.

        Returns:
            str, Nine: None to use the original behavior or a string containing
            an IP address.
        '''
        return None

    @staticmethod
    def accept_url(url_info, record_info, verdict, reasons):
        '''Return whether to download this URL.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            record_info (dict): A mapping containing the same information in
                :class:`.database.URLRecord`.
            verdict (bool): A bool indicating whether Wpull wants to download
                the URL.
            reasons (dict): A dict containing information for the verdict:

                * ``filters`` (dict): A mapping (str to bool) from filter name
                  to whether the filter passed or not.

        Returns:
            bool: If True, the URL should be downloaded. Otherwise, the URL
            is skipped.
        '''
        return verdict

    @staticmethod
    def handle_response(url_info, http_info):
        '''Return an action to handle the response.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            http_info (dict): A mapping containing the same information
                in :class:`.http.Response`.

        Returns:
            str: A value from :class:`Actions`. The default is
            `Actions.NORMAL`.
        '''
        return Actions.NORMAL

    @staticmethod
    def handle_error(url_info, error_info):
        '''Return an action to handle the error.

        Args:
            url_info (dict): A mapping containing the same information in
                :class:`.url.URLInfo`.
            http_info (dict): A mapping containing the keys:

                * ``error``: The name of the exception (for example,
                  ``ProtocolError``)

        Returns:
            str: A value from :class:`Actions`. The default is
            `Actions.NORMAL`.
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
                :class:`.http.Body`.

        .. Note:: The URLs provided do not replace entries in the URL Table.
           If a URL already exists in the URL Table, it will be ignored
           as defined in :class:`.database.URLTable`. As well, the URLs
           added do not reset the item Status to ``todo``. To override
           this behavior, see ``replace`` as described below.

        Returns:
            list: A :class:`list` of :class:`dict`. Each ``dict`` contains:

                * ``url``: a string of the URL
                * ``link_type`` (str, optional): ``html`` or ``None``.
                * ``boolean`` (bool, optional): If True, the link is an
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
    def finishing_statistics(start_time, end_time, num_urls, bytes_downloaded):
        '''Callback containing finial statistics.

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


class HookedResolver(Resolver):
    '''A Resolver containing overridden functions.'''
    def __init__(self, *args, **kwargs):
        self._hook_env = kwargs.pop('hook_env')
        self._callbacks_hook = self._hook_env.callbacks
        super().__init__(*args, **kwargs)

    @tornado.gen.coroutine
    def resolve(self, host, port):
        answer = self._callbacks_hook.resolve_dns(to_lua_type(host))

        _logger.debug('Resolve hook returned {0}'.format(answer))

        if answer:
            family = 10 if ':' in answer else 2
            raise tornado.gen.Return((family, (answer, port)))

        raise tornado.gen.Return((yield super().resolve(host, port)))


class HookedWebProcessor(WebProcessor):
    '''A Web Processor containing overridden functions.'''
    def __init__(self, *args, **kwargs):
        self._hook_env = kwargs.pop('hook_env')
        self._callbacks_hook = self._hook_env.callbacks

        super().__init__(*args, **kwargs)

        self._session_class = HookedWebProcessorSession

    @tornado.gen.coroutine
    def process(self, url_item):
        session = self._session_class(self, url_item)
        session.hook_env = self._hook_env
        session.callbacks_hook = self._callbacks_hook

        raise tornado.gen.Return((yield session.process()))


class HookedWebProcessorSessionMixin(object):
    '''Hooked Web Processor Session Mixin.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hook_env = NotImplemented
        self.callbacks_hook = NotImplemented

    def _to_script_native_type(self, instance):
        '''Convert the instance to script's native types.'''
        return self.hook_env.to_script_native_type(instance)

    def _should_fetch(self):
        verdict = super()._should_fetch()

        # super() may have skipped this already. We undo it.
        self._url_item.set_status(Status.in_progress,
            increment_try_count=False)

        url_info_dict = self._to_script_native_type(
            self._next_url_info.to_dict())

        record_info_dict = self._url_item.url_record.to_dict()
        record_info_dict = self._to_script_native_type(record_info_dict)

        reasons = {
            'filters': self._get_filter_info(),
        }
        reasons = self._to_script_native_type(reasons)

        verdict = self.callbacks_hook.accept_url(
            url_info_dict, record_info_dict, verdict, reasons)

        _logger.debug('Hooked should fetch returned {0}'.format(verdict))

        if not verdict:
            self._url_item.skip()

        return verdict

    def _get_filter_info(self):
        filter_info_dict = {}

        test_info = self._processor.url_filter.test_info(
            self._next_url_info, self._url_item.url_record)

        for filter_instance in test_info['passed']:
            name = filter_instance.__class__.__name__
            filter_info_dict[name] = True

        for filter_instance in test_info['failed']:
            name = filter_instance.__class__.__name__
            filter_info_dict[name] = False

        return filter_info_dict

    def _handle_response(self, response):
        url_info_dict = self._to_script_native_type(
            self._request.url_info.to_dict())
        response_info_dict = self._to_script_native_type(response.to_dict())
        action = self.callbacks_hook.handle_response(
            url_info_dict, response_info_dict)

        _logger.debug('Hooked response returned {0}'.format(action))

        if action == Actions.NORMAL:
            return super()._handle_response(response)
        elif action == Actions.RETRY:
            return False
        elif action == Actions.FINISH:
            self._url_item.set_status(Status.done)
            return True
        elif action == Actions.STOP:
            raise HookStop()
        else:
            raise NotImplementedError()

    def _handle_error(self, error):
        url_info_dict = self._to_script_native_type(
            self._request.url_info.to_dict())
        error_info_dict = self._to_script_native_type({
            'error': error.__class__.__name__,
        })
        action = self.callbacks_hook.handle_error(
            url_info_dict, error_info_dict)

        _logger.debug('Hooked error returned {0}'.format(action))

        if action == Actions.NORMAL:
            return super().handle_error(error)
        elif action == Actions.RETRY:
            return False
        elif action == Actions.FINISH:
            self._url_item.set_status(Status.done)
            return True
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')
        else:
            raise NotImplementedError()

    def _scrape_document(self, request, response):
        super()._scrape_document(request, response)

        to_native = self._to_script_native_type
        filename = to_native(response.body.content_file.name)
        url_info_dict = to_native(self._request.url_info.to_dict())
        document_info_dict = to_native(response.body.to_dict())

        new_url_dicts = self.callbacks_hook.get_urls(
            filename, url_info_dict, document_info_dict)

        _logger.debug('Hooked scrape returned {0}'.format(new_url_dicts))

        if not new_url_dicts:
            return

        if to_native(1) in new_url_dicts:
            # Lua doesn't have sequences
            for i in itertools.count(1):
                new_url_dict = new_url_dicts[to_native(i)]

                _logger.debug('Got lua new url info {0}'.format(new_url_dict))

                if new_url_dict is None:
                    break

                self._add_hooked_url(new_url_dict)
        else:
            for new_url_dict in new_url_dicts:
                self._add_hooked_url(new_url_dict)

    def _add_hooked_url(self, new_url_dict):
        '''Process the ``dict`` from the script and add the URLs.'''
        to_native = self._to_script_native_type
        url = new_url_dict[to_native('url')]
        link_type = self._get_from_native_dict(new_url_dict, 'link_type')
        inline = self._get_from_native_dict(new_url_dict, 'inline')
        post_data = self._get_from_native_dict(new_url_dict, 'post_data')
        replace = self._get_from_native_dict(new_url_dict, 'replace')

        assert url

        url_info = self._parse_url(url, 'utf-8')

        if not url_info:
            return

        kwargs = dict(link_type=link_type, post_data=post_data)

        if replace:
            self._url_item.url_table.remove([url])

        if inline:
            self._url_item.add_inline_url_infos([url_info], **kwargs)
        else:
            self._url_item.add_linked_url_infos([url_info], **kwargs)

    def _get_from_native_dict(self, instance, key, default=None):
        '''Try to get from the mapping a value.

        This method will try to determine whether a Lua table or
        ``dict`` is given.
        '''
        try:
            instance.attribute_should_not_exist
        except AttributeError:
            return instance.get(key, default)
        else:
            # Check if key exists in Lua table
            value_1 = instance[self._to_script_native_type(key)]

            if value_1 is not None:
                return value_1

            value_2 = getattr(instance, self._to_script_native_type(key))

            if value_1 is None and value_2 is None:
                return default
            else:
                return value_1


class HookedWebProcessorSession(HookedWebProcessorSessionMixin,
WebProcessorSession):
    '''Hooked Web Processor Session.'''
    pass


class HookedEngine(Engine):
    '''Hooked Engine.'''
    def __init__(self, *args, **kwargs):
        self._hook_env = kwargs.pop('hook_env')
        self._callbacks_hook = self._hook_env.callbacks
        super().__init__(*args, **kwargs)

    def _compute_exit_code_from_stats(self):
        super()._compute_exit_code_from_stats()
        exit_code = self._callbacks_hook.exit_status(
            self._hook_env.to_script_native_type(self._exit_code)
        )

        _logger.debug('Hooked exit returned {0}.'.format(exit_code))

        self._exit_code = exit_code

    def _print_stats(self):
        super()._print_stats()

        _logger.debug('Hooked print stats.')

        stats = self._statistics

        self._callbacks_hook.finishing_statistics(
            to_lua_type(stats.start_time),
            to_lua_type(stats.stop_time),
            to_lua_type(stats.files),
            to_lua_type(stats.size),
        )


class HookEnvironment(object):
    '''The global instance used by scripts.'''
    def __init__(self, is_lua=False):
        self.is_lua = is_lua
        self.actions = Actions()
        self.callbacks = Callbacks()

    def to_script_native_type(self, instance):
        '''Convert the instance recursively to native script types.

        If the script is Lua, call :func:`to_lua_type`. Otherwise,
        returns instance unchanged.

        Returns:
            instance
        '''
        if self.is_lua:
            return to_lua_type(instance)
        return instance

    def resolver_factory(self, *args, **kwargs):
        '''Return a :class:`HookedResolver`.'''
        return HookedResolver(
            *args,
             hook_env=self,
            **kwargs
        )

    def web_processor_factory(self, *args, **kwargs):
        '''Return a :class:`HookedWebProcessor`.'''
        return HookedWebProcessor(
            *args,
            hook_env=self,
            **kwargs
        )

    def engine_factory(self, *args, **kwargs):
        '''Return a :class:`HookedEngine`.'''
        return HookedEngine(
            *args,
            hook_env=self,
            **kwargs
        )


def to_lua_type(instance):
    '''Convert instance to appropriate Python types for Lua.'''
    return to_lua_table(to_lua_string(to_lua_number(instance)))


def to_lua_string(instance):
    '''If Lua, convert to bytes.'''
    if sys.version_info[0] == 2:
        return wpull.util.to_bytes(instance)
    else:
        return instance


def to_lua_number(instance):
    '''If Lua and Python 2, convert to long.'''
    if sys.version_info[0] == 2:
        if isinstance(instance, int):
            return long(instance)
        elif isinstance(instance, list):
            return list([to_lua_number(item) for item in instance])
        elif isinstance(instance, tuple):
            return tuple([to_lua_number(item) for item in instance])
        elif isinstance(instance, dict):
            return dict(
                [(to_lua_number(key), to_lua_number(value))
                    for key, value in instance.items()])
        return instance
    else:
        return instance


def to_lua_table(instance):
    '''If Lua and instance is ``dict``, convert to Lua table.'''
    if isinstance(instance, dict):
        table = lua.eval('{}')

        for key, value in instance.items():
            table[to_lua_table(key)] = to_lua_table(value)

        return table
    return instance
