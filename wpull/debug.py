# encoding=utf-8
'''Debugging utilities.'''
import html
import io
import sys
import traceback

import tornado.web


class DebugConsoleHandler(tornado.web.RequestHandler):
    TEMPLATE = '''<html>
    <style>
        #commandbox {{
            width: 100%;
        }}
    </style>
    <body>
        <p>Welcome to DEBUG CONSOLE!</p>
        <p><tt>Builder()</tt> instance at <tt>wpull_builder</tt>.</p>
        <form method="post">
            <input id="commandbox" name="command" value="{command}">
            <input type="submit" value="Execute">
        </form>
        <pre>{output}</pre>
    </body>
    </html>
    '''

    def get(self):
        self.write(
            self.TEMPLATE.format(output='(ready)', command='')
            .encode('utf-8'))

    def post(self):
        command = self.get_argument('command', strip=False)
        sys.stdout = io.StringIO()

        try:
            exec(
                command,
                {'wpull_builder': self.application.settings['builder']}
            )
            result = sys.stdout.getvalue()
        except Exception:
            result = traceback.format_exc()
        finally:
            sys.stdout = sys.__stdout__

        self.write(
            self.TEMPLATE.format(output=result, command=html.escape(command))
            .encode('utf-8'))
