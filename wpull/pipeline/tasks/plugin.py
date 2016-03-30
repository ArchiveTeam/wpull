import asyncio
import gettext
import inspect
import logging

from yapsy.PluginManager import PluginManager

from wpull.application.hook import HookableMixin
from wpull.backport.logging import BraceMessage as __
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class PluginSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        session.plugin_manager = PluginManager(plugin_info_ext='wpull-plugin')

        if session.args.plugin_script:
            session.plugin_manager.setPluginPlaces([session.args.plugin_script])

        session.plugin_manager.collectPlugins()

        for plugin_info in session.plugin_manager.getAllPlugins():
            _logger.info(__(
                _('Found plugin {name} from {filename}.'),
                filename=plugin_info.path,
                name=plugin_info.name
            ))

            plugin_info.plugin_object.app_session = session
            session.plugin_manager.activatePluginByName(plugin_info.name)
            cls._connect_plugin_hooks(session, plugin_info.plugin_object)

    @classmethod
    def _connect_plugin_hooks(cls, session: AppSession, plugin_object):
        for callback_func in cls._get_plugin_callbacks(plugin_object):
            dispatcher = cls._get_dispatcher(
                session, callback_func.callback_name,
                callback_func.callback_category
            )

            if not dispatcher:
                continue

            if callback_func.callback_category == 'hook':
                dispatcher.connect(callback_func.callback_name, callback_func)
            else:
                dispatcher.listen(callback_func.callback_name, callback_func)

    @classmethod
    def _get_plugin_callbacks(cls, plugin_object):
        funcs = inspect.getmembers(plugin_object, predicate=inspect.ismethod)

        for func in funcs:
            if hasattr(func, 'callback_name'):
                yield func

    @classmethod
    def _get_dispatcher(cls, session: AppSession, name: str,
                        callback_category: str):
        for instance in session.factory.instance_map.values():
            if not isinstance(instance, HookableMixin):
                continue

            if callback_category == 'hook':
                if instance.hook_dispatcher.is_registered(name):
                    return instance.hook_dispatcher
            else:
                if instance.event_dispatcher.is_registered(name):
                    return instance.event_dispatcher
