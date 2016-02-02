
import asyncio

from wpull.app import Application


class MyApplication(Application):
    @asyncio.coroutine
    def run(self):
        yield from super().run()
        return 42


wpull_plugin.factory.class_map['Application'] = MyApplication
