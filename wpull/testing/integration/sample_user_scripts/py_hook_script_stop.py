# encoding=utf-8


wpull_hook = globals().get('wpull_hook')  # silence code checkers


def handle_response(url_info, record_info, http_info):
    print('handle_response', url_info)

    return wpull_hook.actions.STOP

wpull_hook.callbacks.handle_response = handle_response
