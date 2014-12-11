# encoding=utf-8
import os.path


wpull_hook = globals().get('wpull_hook')  # silence code checkers
wpull_hook.callbacks.version = 2

counter = 0
injected_url_found = False
got_redirected_page = False


def engine_run():
    assert wpull_hook.factory['Engine']
    wpull_hook.factory['Engine'].set_concurrent(2)


def resolve_dns(host):
    print('resolve_dns', host)
    assert host == 'localhost'
    return '127.0.0.1'


def accept_url(url_info, record_info, verdict, reasons):
    print('accept_url', url_info)
    assert url_info['url']

    if 'mailto:' in url_info['url']:
        assert not verdict
        assert not reasons['filters']['SchemeFilter']
    else:
        assert url_info['path'] in (
            '/robots.txt', '/', '/post/',
            '/%95%B6%8E%9A%89%BB%82%AF/',
            '/static/style.css', '/wolf',
            '/some_page', '/some_page/',
            '/mordor',
            )
        assert reasons['filters']['SchemeFilter']

    assert record_info['url']

    for name, passed in reasons['filters'].items():
        assert name

    if url_info['path'] == '/':
        assert not record_info['inline']
        assert verdict
    elif url_info['path'] == '/post/':
        assert not verdict
        verdict = True
    elif url_info['path'] == '/static/style.css':
        assert record_info['inline']
    elif url_info['path'] == '/robots.txt':
        verdict = False

    return verdict


def queued_url(url_info):
    print('queued_url', url_info)
    assert url_info['url']

    global counter
    counter += 1

    assert counter > 0


def dequeued_url(url_info, record_info):
    print('dequeued_url', url_info)
    assert url_info['url']
    assert record_info['url']

    global counter
    counter -= 1

    assert counter >= 0


def handle_pre_response(url_info, record_info, http_info):
    if url_info['path'] == '/mordor':
        return wpull_hook.actions.FINISH

    return wpull_hook.actions.NORMAL


def handle_response(url_info, record_info, http_info):
    print('handle_response', url_info)

    if url_info['path'] == '/':
        assert http_info['body']['content_size']
        assert http_info['status_code'] == 200
    elif url_info['path'] == '/post/':
        assert http_info['status_code'] == 200
        global injected_url_found
        injected_url_found = True
        return wpull_hook.actions.FINISH
    elif url_info['path'] == '/some_page/':
        global got_redirected_page
        got_redirected_page = True

    return wpull_hook.actions.NORMAL


def handle_error(url_info, record_info, error_info):
    print('handle_response', url_info, error_info)
    assert error_info['error']
    return wpull_hook.actions.NORMAL


def get_urls(filename, url_info, document_info):
    print('get_urls', filename)
    assert filename
    assert os.path.isfile(filename)
    assert url_info['url']

    if url_info['path'] == '/':
        return [
            {
                'url':
                'http://localhost:' + str(url_info['port']) + '/post/',
                'inline': True,
                'post_data': 'text=hello',
                'replace': True,
            },
            {
                'url': '..malformed',
            }
        ]

    return None


def wait_time(seconds):
    assert seconds >= 0
    return 0


def finish_statistics(start_time, end_time, num_urls, bytes_downloaded):
    print('finish_statistics', start_time)
    assert start_time
    assert end_time

    global counter
    print('queue counter', counter)
    assert counter == 0


def exit_status(exit_code):
    assert exit_code == 4
    assert injected_url_found
    assert got_redirected_page
    print('exit_status', exit_code)
    return 42


wpull_hook.callbacks.engine_run = engine_run
wpull_hook.callbacks.resolve_dns = resolve_dns
wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.queued_url = queued_url
wpull_hook.callbacks.dequeued_url = dequeued_url
wpull_hook.callbacks.handle_pre_response = handle_pre_response
wpull_hook.callbacks.handle_response = handle_response
wpull_hook.callbacks.handle_error = handle_error
wpull_hook.callbacks.get_urls = get_urls
wpull_hook.callbacks.wait_time = wait_time
wpull_hook.callbacks.finish_statistics = finish_statistics
wpull_hook.callbacks.exit_status = exit_status
