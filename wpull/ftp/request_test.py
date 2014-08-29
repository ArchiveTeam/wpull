import unittest
from wpull.ftp.request import Reply, Command


class TestRequest(unittest.TestCase):
    def test_parse_reply(self):
        reply = Reply()
        reply.parse(b'200 Hello\r\n')

        self.assertEqual(200, reply.code)
        self.assertEqual('Hello', reply.text)

        reply = Reply()
        reply.parse(b'200-Hello\r\n')
        reply.parse(b'200 World!\r\n')

        self.assertEqual(200, reply.code)
        self.assertEqual('Hello\r\nWorld!', reply.text)

        reply = Reply()
        reply.parse(b'200-Hello\r\n')
        reply.parse(b'F\r\n')
        reply.parse(b' T\r\n')
        reply.parse(b'200-P\r\n')
        reply.parse(b'200 World!\r\n')

        self.assertEqual(200, reply.code)
        self.assertEqual('Hello\r\nF\r\nT\r\nP\r\nWorld!', reply.text)

        self.assertRaises(AssertionError, reply.parse, b'200 Hello again')

    def test_reply(self):
        reply = Reply(200, 'Hello world!\nFerret transfer protocol')
        self.assertEqual(
            b'200-Hello world!\r\n200 Ferret transfer protocol\r\n',
            reply.to_bytes()
        )
        self.assertEqual(200, reply.to_dict()['code'])
        self.assertEqual(
            'Hello world!\nFerret transfer protocol',
            reply.to_dict()['text']
        )

    def test_parse_command(self):
        command = Command()
        command.parse(b'User narwhal@compuwhal.org\r\n')

        self.assertEqual('USER', command.name)
        self.assertEqual('narwhal@compuwhal.org', command.argument)

        self.assertRaises(AssertionError, command.parse, b'OOPS\r\n')

        command = Command()
        command.parse(b'POKE\r\n')

        self.assertEqual('POKE', command.name)
        self.assertEqual('', command.argument)

        self.assertRaises(AssertionError, command.parse, b'OOPS\r\n')

    def test_command(self):
        command = Command('User', 'narwhal@compuwhal.org')
        self.assertEqual('USER', command.name)
        self.assertEqual('narwhal@compuwhal.org', command.argument)

        self.assertEqual('USER', command.to_dict()['name'])
        self.assertEqual(
            'narwhal@compuwhal.org', command.to_dict()['argument'])

        command = Command('Poke')
        self.assertEqual('POKE', command.name)
        self.assertEqual('', command.argument)

        self.assertEqual('POKE', command.to_dict()['name'])
        self.assertEqual('', command.to_dict()['argument'])
