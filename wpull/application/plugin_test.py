import unittest

from wpull.application.plugin import WpullPlugin, hook, event, InterfaceRegistry, \
    event_interface, PluginClientFunctionInfo, PluginFunctionCategory


class MockPlugin(WpullPlugin):
    @hook('hook_thing')
    def my_hook_callback(self):
        pass

    @event('event_thing')
    def my_event_callback(self, data):
        pass

    def unrelated_function(self):
        pass


class TestPlugin(unittest.TestCase):
    def test_plugin_function_discovery(self):
        plugin = MockPlugin()

        funcs = list(plugin.get_plugin_functions())
        self.assertEqual(2, len(funcs))
        self.assertIn(
            PluginClientFunctionInfo(
                plugin.my_event_callback, 'event_thing',
                PluginFunctionCategory.event),
            funcs)
        self.assertIn(
            PluginClientFunctionInfo(
                plugin.my_hook_callback, 'hook_thing',
                PluginFunctionCategory.hook),
            funcs)

    def test_plugin_interface_registry(self):
        registry = InterfaceRegistry()

        @event_interface('test_event', registry)
        def event_callback(data):
            pass

        self.assertEqual(1, len(registry))
        self.assertIn('test_event', registry)
