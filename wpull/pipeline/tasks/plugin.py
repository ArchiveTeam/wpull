import asyncio
import gettext
import inspect
import logging
import os
import re
from configparser import ConfigParser

from yapsy.IPluginLocator import IPluginLocator
from yapsy.PluginFileLocator import PluginFileAnalyzerMathingRegex, \
    PluginFileLocator
from yapsy.PluginInfo import PluginInfo
from yapsy.PluginManager import PluginManager

from wpull.application.hook import HookableMixin
from wpull.application.plugin import WpullPlugin
from wpull.backport.logging import BraceMessage as __
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession
from wpull.util import get_package_filename

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class PluginLocator(IPluginLocator):
    def __init__(self, directories, paths):
        self._directories = directories
        self._paths = paths

    def locatePlugins(self):
        candidates = []

        for directory in self._directories:
            for filename in os.listdir(directory):
                path = os.path.join(directory, filename)

                if os.path.isfile(path) and self._is_plugin_filename(filename):
                    info = self._plugin_info_from_path(path)
                    candidates.append((path, path, info))

        for filename in self._paths:
            info = self._plugin_info_from_path(filename)
            candidates.append((path, filename, info))

        return candidates, len(candidates)

    @classmethod
    def _is_plugin_filename(cls, filename):
        return re.match('.+\.plugin\.py', filename)

    @classmethod
    def _plugin_info_from_path(cls, path):
        name = re.sub(r'[^\w]|:', '_', os.path.basename(path))
        info = PluginInfo(name, path)
        return info

    def gatherCorePluginInfo(self, directory, filename):
        info = self._plugin_info_from_path(os.path.join(directory, filename))
        config = ConfigParser()
        config.add_section("Core")
        config.set("Core", "Name", info.name)
        config.set("Core", "Module", info.path)

        return info, config


class PluginSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        plugin_locations = [get_package_filename(os.path.join('application', 'plugins'))]

        plugin_filenames = []

        if session.args.plugin_script:
            plugin_filenames.append(session.args.plugin_script)

        locator = PluginLocator(plugin_locations, plugin_filenames)

        session.plugin_manager = PluginManager(plugin_locator=locator)
        session.plugin_manager.collectPlugins()

        for plugin_info in session.plugin_manager.getAllPlugins():
            _logger.info(__(
                _('Found plugin {name} from {filename}.'),
                filename=plugin_info.path,
                name=plugin_info.name
            ))

            plugin_info.plugin_object.app_session = session

            if plugin_info.plugin_object.should_activate():
                session.plugin_manager.activatePluginByName(plugin_info.name)
                self._connect_plugin_hooks(session, plugin_info.plugin_object)

    @classmethod
    def _connect_plugin_hooks(cls, session: AppSession, plugin_object: WpullPlugin):
        for instance in session.factory.instance_map.values():
            if not isinstance(instance, HookableMixin):
                continue

            instance.connect_plugin(plugin_object)
