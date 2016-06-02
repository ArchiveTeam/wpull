.. _scripting-hooks:

Scripting Hooks
===============

Wpull's scripting support is modelled after `alard's Wget with Lua
hooks <https://github.com/alard/wget-lua/wiki/Wget-with-Lua-hooks>`_.

Scripts are installed using the `YAPSY plugin
<http://yapsy.sourceforge.net/>`_ architecture. To create your plugin
script, subclass :py:class:`wpull.application.plugin.WpullPlugin` and
load it with ``--plugin-script`` option.

The plugin interface provides two type of callbacks: hooks and events.


Hook
++++

Hooks change the behavior of the program. When the callback is
registered to the hook, it is required to provide a return value
typically one of :py:class:`wpull.application.hook.Actions`. Only
one callback may be registered to a hook.

To register your callback, decorate your callback with
:py:func:`wpull.application.plugin.hook`.


Event
+++++

Events are points in the program that occur and are notified to
registered listeners.

To register your callback, decorate your callback with
:py:func:`wpull.application.plugin.event`.


Interfaces
++++++++++

The global hooks and events constants are located at
:py:class:`wpull.application.plugin.PluginFunctions`.

TODO: document the hooks available

The module providing the interface for user plugins is located
at :py:mod:`wpull.application.plugin` and the interface for code
is located at :py:mod:`wpull.application.hook`.

Example
+++++++

Here is a example Python script. It refuses to download anything with the word "dog" in the URL::

    from wpull.application.plugin import WpullPlugin, PluginFunctions, hook
    from wpull.protocol.abstract.request import BaseResponse
    from wpull.pipeline.session import ItemSession

    class PrintServerResponsePlugin(WpullPlugin):
        @hook(PluginFunctions.accept_url)
        def my_accept_func(self, item_session: ItemSession, verdict: bool, reasons: dict) -> bool:
            return 'dog' not in item_session.request.url


For an example, see `ArchiveBot's scripting hook file <https://github.com/ArchiveTeam/ArchiveBot/blob/065b0cc2549224f72a16cd3611fffb2050962c74/pipeline/wpull_hooks.py>`_.

