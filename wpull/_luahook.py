'''Script hook adapter for lua.'''
import sys

import wpull.string
import itertools


def load_lua():
    '''Load the Lua module.

    .. seealso:: http://stackoverflow.com/a/8403467/1524507
    '''
    import DLFCN
    sys.setdlopenflags(DLFCN.RTLD_NOW | DLFCN.RTLD_GLOBAL)
    import lua
    return lua


def to_lua_type(instance):
    '''Convert instance to appropriate Python types for Lua.'''
    return to_lua_table(to_lua_string(to_lua_number(instance)))


def to_lua_string(instance):
    '''If Lua, convert to bytes.'''
    if sys.version_info[0] == 2:
        return wpull.string.to_bytes(instance)
    else:
        return instance


def to_lua_number(instance):
    '''If Lua and Python 2, convert to long.'''
    if sys.version_info[0] == 2:
        if instance is True or instance is False:
            return instance
        elif isinstance(instance, int):
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


def from_lua_table_to_list(instance):
    # Lua doesn't have sequences
    items = []
    for i in itertools.count(1):
        item = instance[to_lua_type(i)]

        if item is None:
            break

        items.append(item)

    return items


def get_from_lua_table_as_dict(instance, key, default=None):
    '''Try to get from the mapping a value.

    This method will try to determine whether a Lua table or
    ``dict`` is given.
    '''
    # Check if key exists in Lua table
    value_1 = instance[to_lua_type(key)]

    if value_1 is not None:
        return value_1

    value_2 = getattr(instance, to_lua_type(key))

    if value_1 is None and value_2 is None:
        return default
    else:
        return value_1


def install(lua_script_path):
    class CallbacksAdapter(object):
        AVAILABLE_VERSIONS = to_lua_number(wpull_hook.callbacks.AVAILABLE_VERSIONS)

        @property
        def version(self):
            return wpull_hook.version

        @version.setter
        def version(self, num):
            wpull_hook.version = num

        engine_run = NotImplemented
        resolve_dns = NotImplemented
        accept_url = NotImplemented
        queued_url = NotImplemented
        dequeued_url = NotImplemented
        handle_pre_response = NotImplemented
        handle_response = NotImplemented
        handle_error = NotImplemented
        get_urls = NotImplemented
        wait_time = NotImplemented
        finishing_statistics = NotImplemented
        exit_status = NotImplemented

    callbacks = CallbacksAdapter()

    class HookEnvironmentAdapter(object):
        factory = wpull_hook.factory
        actions = wpull_hook.actions

        @staticmethod
        def engine_run():
            if callbacks.engine_run is not NotImplemented:
                callbacks.engine_run()

        @staticmethod
        def resolve_dns(host):
            if callbacks.resolve_dns is not NotImplemented:
                return callbacks.resolve_dns(to_lua_type(host))

        @staticmethod
        def accept_url(url_info, record_info, verdict, reasons):
            if callbacks.accept_url is not NotImplemented:
                return callbacks.accept_url(
                    to_lua_type(url_info),
                    to_lua_type(record_info),
                    verdict,
                    to_lua_type(reasons)
                    )

        @staticmethod
        def queued_url(url_info):
            if callbacks.queued_url is not NotImplemented:
                callbacks.queued_url(to_lua_type(url_info))

        @staticmethod
        def dequeued_url(url_info, record_info):
            if callbacks.dequeued_url is not NotImplemented:
                callbacks.dequeued_url(
                    to_lua_type(url_info), to_lua_type(record_info))

        @staticmethod
        def handle_pre_response(url_info, record_info, http_info):
            if callbacks.handle_pre_response is not NotImplemented:
                return callbacks.handle_pre_response(
                    to_lua_type(url_info),
                    to_lua_type(record_info),
                    to_lua_type(http_info)
                    )
            else:
                return 'normal'

        @staticmethod
        def handle_response(url_info, record_info, http_info):
            if callbacks.handle_response is not NotImplemented:
                return callbacks.handle_response(
                    to_lua_type(url_info),
                    to_lua_type(record_info),
                    to_lua_type(http_info)
                    )
            else:
                return 'normal'

        @staticmethod
        def handle_error(url_info, record_info, error_info):
            if callbacks.handle_error is not NotImplemented:
                return callbacks.handle_error(
                    to_lua_type(url_info),
                    to_lua_type(record_info),
                    to_lua_type(error_info)
                    )
            else:
                return 'normal'

        @staticmethod
        def get_urls(filename, url_info, document_info):
            if callbacks.get_urls is not NotImplemented:
                result = (callbacks.get_urls(
                    to_lua_type(filename),
                    to_lua_type(url_info),
                    to_lua_type(document_info)
                    ))

                if result:
                    lua_items = from_lua_table_to_list(result)

                    items = []

                    for lua_item in lua_items:
                        item = {
                            'url': get_from_lua_table_as_dict(lua_item, 'url'),
                            'link_type': get_from_lua_table_as_dict(
                                lua_item, 'link_type'),
                            'inline': get_from_lua_table_as_dict(
                                lua_item, 'inline'),
                            'post_data': get_from_lua_table_as_dict(
                                lua_item, 'post_data'),
                            'replace': get_from_lua_table_as_dict(
                                lua_item, 'replace'),
                        }
                        items.append(item)

                    return items

        @staticmethod
        def wait_time(seconds):
            if callbacks.wait_time is not NotImplemented:
                return callbacks.wait_time(to_lua_type(seconds))
            else:
                return seconds

        @staticmethod
        def finishing_statistics(start_time, end_time, num_urls, bytes_downloaded):
            if callbacks.finishing_statistics is not NotImplemented:
                callbacks.finishing_statistics(
                    to_lua_type(start_time),
                    to_lua_type(end_time),
                    to_lua_type(num_urls),
                    to_lua_type(bytes_downloaded)
                    )

        @staticmethod
        def exit_status(exit_code):
            if callbacks.exit_status is not NotImplemented:
                return callbacks.exit_status(to_lua_type(exit_code))
            else:
                return exit_code

    wpull_hook.callbacks.engine_run = HookEnvironmentAdapter.engine_run
    wpull_hook.callbacks.resolve_dns = HookEnvironmentAdapter.resolve_dns
    wpull_hook.callbacks.accept_url = HookEnvironmentAdapter.accept_url
    wpull_hook.callbacks.queued_url = HookEnvironmentAdapter.queued_url
    wpull_hook.callbacks.dequeued_url = HookEnvironmentAdapter.dequeued_url
    wpull_hook.callbacks.handle_pre_response = HookEnvironmentAdapter.handle_pre_response
    wpull_hook.callbacks.handle_response = HookEnvironmentAdapter.handle_response
    wpull_hook.callbacks.handle_error = HookEnvironmentAdapter.handle_error
    wpull_hook.callbacks.get_urls = HookEnvironmentAdapter.get_urls
    wpull_hook.callbacks.wait_time = HookEnvironmentAdapter.wait_time
    wpull_hook.callbacks.finishing_statistics = HookEnvironmentAdapter.finishing_statistics
    wpull_hook.callbacks.exit_status = HookEnvironmentAdapter.exit_status

    global lua
    lua = load_lua()
    lua_globals = lua.globals()
    lua_globals.wpull_hook = HookEnvironmentAdapter()
    lua_globals.wpull_hook.callbacks = callbacks

    with open(lua_script_path, 'rb') as in_file:
        lua.execute(in_file.read())
