===
API
===

Wpull was designed as a command line program and most users do not need to read this section. However, you may be using the scripting hook interface or you may want to reuse a component.

Since Wpull is generally not a library, API backwards compatibility is provided on a best-effort basis; there is no guarantee on whether public or private functions will remain the same. This rule does not include the scripting hook interface which is designed for backwards compatibility.

Here lists all documented classes and functions. Not all members are documented yet. Some members, such as the backported modules, are not documented here.

If the documentation is not sufficient, please take a look at the source code. Suggestions and improvements are welcomed.

.. Note:: The API is not thread-safe. It is intended to be run asynchronously with Asyncio.

    Many functions also are decorated with the :func:`asyncio.coroutine` decorator. For more information, see https://docs.python.org/3/library/asyncio.html.


wpull Package
=============

.. toctree::
    :glob:

    api/*

