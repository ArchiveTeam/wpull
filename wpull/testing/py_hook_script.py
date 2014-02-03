# encoding=utf-8
import os.path


wpull_hook = globals().get('wpull_hook')  # silence code checkers
injected_url_found = False


def resolve_dns(host):
    print('resolve_dns', host)
    assert host == 'localhost'
    return '127.0.0.1'


def accept_url(url_info, record_info, verdict, reasons):
    print('accept_url', url_info)
    assert url_info['url']
    assert url_info['path'] in ('/robots.txt', '/', '/post/',
        '/%95%B6%8E%9A%89%BB%82%AF/', '/static/style.css')
    assert record_info['url']
    assert reasons['filters']['HTTPFilter']

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


def handle_response(url_info, http_info):
    print('handle_response', url_info)

    if url_info['path'] == '/':
        assert http_info['body']['content_size']
        assert http_info['status_code'] == 200
    elif url_info['path'] == '/post/':
        assert http_info['status_code'] == 200
        global injected_url_found
        injected_url_found = True
        return wpull_hook.actions.FINISH

    return wpull_hook.actions.NORMAL


def handle_error(url_info, error_info):
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
        }]

    return None


def finish_statistics(start_time, end_time, num_urls, bytes_downloaded):
    print('finish_statistics', start_time)
    assert start_time
    assert end_time


def exit_status(exit_code):
    assert exit_code == 0
    assert injected_url_found
    print('exit_status', exit_code)
    return 42


wpull_hook.callbacks.resolve_dns = resolve_dns
wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.handle_response = handle_response
wpull_hook.callbacks.handle_error = handle_error
wpull_hook.callbacks.get_urls = get_urls
wpull_hook.callbacks.finish_statistics = finish_statistics
wpull_hook.callbacks.exit_status = exit_status
