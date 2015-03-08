.. _scripting-hooks:

Scripting Hooks
===============

Wpull's scripting support is modelled after `alard's Wget with Lua hooks <https://github.com/alard/wget-lua/wiki/Wget-with-Lua-hooks>`_.

When the script is loaded, a global instance ``wpull_hook`` (:py:class:`wpull.hook.HookEnvironment`) will be available. The ``wpull_hook`` instance contains members where two of them are most useful:

* ``callbacks``: Callback functions that serve as hooks to change functionality. These should be overridden if needed. ``callbacks`` is actually an instance of :py:class:`wpull.hook.Callbacks`.
* ``actions``: Constants needed for some functions. ``actions`` is actually an instance of :py:class:`wpull.hook.Actions`.

Here is a example Python script. It refuses to download anything with the word "dog" in it::

    def accept_url(url_info, record_info, verdict, reasons):
        if 'dog' in url_info['url']:
            return False
        else:
            return verdict

    wpull_hook.callbacks.accept_url = accept_url

Here is the same script, but in Lua:

.. code-block:: lua

    wpull_hook.callbacks.accept_url = function(url_info, record_info, verdict, reasons)
        if string.match(url_info['url'], 'dog') then
            return false
        else
            return verdict
        end
    end

Wpull will attempt to support deprecation and feature selection through Scripting API Versions. To select a version, include in your script::

    wpull_hook.callbacks.version = 2

For complete details, see :py:mod:`wpull.hook`. For an example, see `ArchiveBot's scripting hook file <https://github.com/ArchiveTeam/ArchiveBot/blob/065b0cc2549224f72a16cd3611fffb2050962c74/pipeline/wpull_hooks.py>`_.

