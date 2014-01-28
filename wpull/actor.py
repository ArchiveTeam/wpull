# encoding=utf-8


class Event(object):
    '''Simple event system.

    :seealso: http://www.valuedlessons.com/2008/04/events-in-python.html
    '''
    def __init__(self):
        super().__init__()
        self.handlers = set()

    def handle(self, handler):
        '''Registers a callback function.'''
        self.handlers.add(handler)
        return self

    def unhandle(self, handler):
        '''Unregisters a callback function.'''
        try:
            self.handlers.remove(handler)
        except:
            raise ValueError(
                "Handler is not handling this event, so cannot unhandle it.")
        return self

    def fire(self, *args, **kargs):
        '''Invokes all the callback functions.'''
        for handler in self.handlers:
            handler(*args, **kargs)

    def get_handler_count(self):
        '''Returns the number of callback functions registered.'''
        return len(self.handlers)

    def clear(self):
        '''Unregisters all callback functions.'''
        self.handlers.clear()

    __iadd__ = handle
    __isub__ = unhandle
    __call__ = fire
    __len__ = get_handler_count
