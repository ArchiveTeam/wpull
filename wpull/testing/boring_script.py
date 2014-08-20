assert wpull_hook


counter = 0

def queued_url(url_info):
    global counter
    counter += 1
    print('queued_url', counter, url_info['url'])


def dequeued_url(url_info, record_info):
    global counter
    counter -= 1
    print('dequeued_url', counter, url_info['url'])


wpull_hook.callbacks.queued_url = queued_url
wpull_hook.callbacks.dequeued_url = dequeued_url
