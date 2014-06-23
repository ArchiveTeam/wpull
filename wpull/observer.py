# encoding=utf-8
'''Observer.'''


class Observer(object):
    '''Observer.

    Args:
        handlers: Callback functions.
    '''
    def __init__(self, *handlers):
        super().__init__()
        self.handlers = set(handlers)

    def clear(self):
        '''Remove all callback handlers.'''
        self.handlers.clear()

    def add(self, handler):
        '''Register a callback function.'''
        self.handlers.add(handler)

    def remove(self, handler):
        '''Unregister a callback function.'''
        self.handlers.remove(handler)

    def notify(self, *args, **kwargs):
        '''Call all the callback handlers with given arguments.'''
        for handler in tuple(self.handlers):
            handler(*args, **kwargs)

    def count(self):
        '''Return the number register handlers.'''
        return len(self.handlers)
