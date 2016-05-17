# encoding=utf-8
from wpull.application.hook import Actions
from wpull.application.plugin import WpullPlugin, PluginFunctions, hook


class MyPlugin(WpullPlugin):
    @hook(PluginFunctions.handle_response)
    def stop(self):
        print('stop')
        return Actions.STOP
