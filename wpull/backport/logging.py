# encoding=utf-8
'''Logging.'''

import logging

# https://docs.python.org/3/howto/logging-cookbook.html#use-of-alternative-formatting-styles


class BraceMessage:
    def __init__(self, fmt, *args, **kwargs):
        self.fmt = fmt
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return self.fmt.format(*self.args, **self.kwargs)


class DollarMessage:
    def __init__(self, fmt, **kwargs):
        self.fmt = fmt
        self.kwargs = kwargs

    def __str__(self):
        from string import Template
        return Template(self.fmt).substitute(**self.kwargs)


class StyleAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra=None):
        super(StyleAdapter, self).__init__(logger, extra or {})

    def log(self, level, msg, *args, **kwargs):
        if self.isEnabledFor(level):
            msg, msg_kwargs, kwargs = self._process_args(msg, kwargs)
            self.logger._log(level, BraceMessage(msg, *args, **msg_kwargs), (), **kwargs)

    def _process_args(self, msg, kwargs):
        # See http://stackoverflow.com/a/24683360 for details
        msg_kwargs = kwargs
        kwargs = dict(
            (key, value) for key, value in kwargs.items()
            if key in ('level', 'msg', 'args', 'exc_info', 'extra',
                       'stack_info')
        )
        kwargs['extra'] = self.extra

        return msg, msg_kwargs, kwargs
