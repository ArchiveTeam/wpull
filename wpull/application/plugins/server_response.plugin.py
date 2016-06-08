from wpull.application.plugin import WpullPlugin, PluginFunctions, event
from wpull.protocol.abstract.request import BaseResponse


class PrintServerResponsePlugin(WpullPlugin):
    def should_activate(self):
        return self.app_session.args.server_response

    @event(PluginFunctions.handle_pre_response)
    def print_response(self, response: BaseResponse):
        print(str(response))
