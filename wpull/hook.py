import contextlib
import logging
import tornado.gen

from wpull.engine import Engine
from wpull.network import Resolver
from wpull.processor import WebProcessor, WebProcessorSession


_logger = logging.getLogger(__name__)


class HookStop(Exception):
    pass


class Actions(object):
    NORMAL = 'normal'
    RETRY = 'retry'
    FINISH = 'finish'
    STOP = 'stop'


class Callbacks(object):
    @staticmethod
    def resolve_dns(host):
        return None

    @staticmethod
    def accept_url(url_info, record_info, verdict, reasons):
        return verdict

    @staticmethod
    def handle_response(url_info, http_info):
        return Actions.NORMAL

    @staticmethod
    def handle_error(url_info, error):
        return Actions.NORMAL

    @staticmethod
    def get_urls(filename, url_info, document_info):
        return None

    @staticmethod
    def finishing_statistics(start_time, end_time, num_urls, bytes_downloaded):
        pass

    @staticmethod
    def exit_status(exit_code):
        return exit_code


class HookedResolver(Resolver):
    def __init__(self, *args, **kwargs):
        self._callbacks_hook = kwargs.pop('callbacks_hook')
        super().__init__(*args, **kwargs)

    @tornado.gen.coroutine
    def resolve(self, host, port):
        answer = self._callbacks_hook.resolve_dns(host)

        _logger.debug('Resolve hook returned {0}'.format(answer))

        if answer:
            family = 10 if ':' in answer else 2
            raise tornado.gen.Return((family, (answer, port)))

        raise tornado.gen.Return((yield super().resolve(host, port)))


class HookedWebProcessor(WebProcessor):
    def __init__(self, *args, **kwargs):
        self._callbacks_hook = kwargs.pop('callbacks_hook')

        super().__init__(*args, **kwargs)

        if self._robots_txt_pool:
            self._session_class = HookedWebProcessorWithRobotsTxtSession
        else:
            self._session_class = HookedWebProcessorSession

    @contextlib.contextmanager
    def session(self, url_item):
        with super().session(url_item) as session:
            session.callbacks_hook = self._callbacks_hook
            yield session


class HookedWebProcessorSessionMixin(object):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.callbacks_hook = NotImplemented

    def should_fetch(self):
        verdict = super().should_fetch()
        url_info_dict = self._next_url_info.to_dict()
        record_info_dict = self._url_item.url_record.to_dict()
        reasons = {
            'filters': self._get_filter_info(),
        }

        verdict = self.callbacks_hook.accept_url(
            url_info_dict, record_info_dict, verdict, reasons)

        _logger.debug('Hooked should fetch returned {0}'.format(verdict))

        return verdict

    def _get_filter_info(self):
        filter_info_dict = {}

        passed, failed = self._filter_url(
            self._next_url_info, self._url_item.url_record)

        for filter_instance in passed:
            name = filter_instance.__class__.__name__
            filter_info_dict[name] = True

        for filter_instance in failed:
            name = filter_instance.__class__.__name__
            filter_info_dict[name] = False

        return filter_info_dict

    def handle_response(self, response):
        url_info_dict = self._next_url_info.to_dict()
        response_info_dict = response.to_dict()
        action = self.callbacks_hook.handle_response(
            url_info_dict, response_info_dict)

        _logger.debug('Hooked response returned {0}'.format(action))

        if action == Actions.NORMAL:
            return super().handle_response(response)
        elif action == Actions.RETRY:
            return False
        elif action == Actions.FINISH:
            return True
        elif action == Actions.STOP:
            raise HookStop()
        else:
            raise NotImplementedError()

    def handle_error(self, error):
        url_info_dict = self._next_url_info.to_dict()
        error_info_dict = {
            'error', error.__class__.__name__,
        }
        action = self.callbacks_hook.handle_error(
            url_info_dict, error_info_dict)

        _logger.debug('Hooked error returned {0}'.format(action))

        if action == Actions.NORMAL:
            return super().handle_error(error)
        elif action == Actions.RETRY:
            return False
        elif action == Actions.FINISH:
            return True
        elif action == Actions.STOP:
            raise HookStop()
        else:
            raise NotImplementedError()

    def _scrape_document(self, request, response):
        inline_urls, linked_urls = super()._scrape_document(request, response)

        filename = response.body.content_file.name
        url_info_dict = self._next_url_info.to_dict()
        document_info_dict = {}

        new_urls = self.callbacks_hook.get_urls(
            filename, url_info_dict, document_info_dict)

        for new_url_dict in new_urls or ():
            linked_urls.add(new_url_dict['url'])

        _logger.debug('Hooked scrape returned {0}'.format(new_urls))

        return inline_urls, linked_urls


class HookedWebProcessorSession(HookedWebProcessorSessionMixin,
WebProcessorSession):
    pass


class HookedWebProcessorWithRobotsTxtSession(
HookedWebProcessorSessionMixin, WebProcessorSession):
    pass


class HookedEngine(Engine):
    def __init__(self, *args, **kwargs):
        self._callbacks_hook = kwargs.pop('callbacks_hook')
        super().__init__(*args, **kwargs)

    def _compute_exit_code_from_stats(self):
        super()._compute_exit_code_from_stats()
        exit_code = self._callbacks_hook.exit_status(self._exit_code)

        _logger.debug('Hooked exit returned {0}.'.format(exit_code))

        self._exit_code = exit_code

    def _print_stats(self):
        super()._print_stats()

        _logger.debug('Hooked print stats.')

        stats = self._processor.statistics

        self._callbacks_hook.finishing_statistics(
            stats.start_time, stats.stop_time, stats.files, stats.size)


class HookEnvironment(object):
    def __init__(self):
        self.actions = Actions()
        self.callbacks = Callbacks()

    def resolver_factory(self, *args, **kwargs):
        return HookedResolver(
            *args,
             callbacks_hook=self.callbacks,
            **kwargs
        )

    def web_processor_factory(self, *args, **kwargs):
        return HookedWebProcessor(
            *args,
            callbacks_hook=self.callbacks,
            **kwargs
        )

    def engine_factory(self, *args, **kwargs):
        return HookedEngine(
            *args,
            callbacks_hook=self.callbacks,
            **kwargs
        )
