from yapsy.IPlugin import IPlugin


class WpullPlugin(IPlugin):
    def __init__(self):
        super().__init__()
        self.app_session = None
