from trollius import From, Return
import trollius

from wpull.app import Application


class MyApplication(Application):
    @trollius.coroutine
    def run(self):
        yield From(super().run())
        raise Return(42)


wpull_plugin.factory.class_map['Application'] = MyApplication
