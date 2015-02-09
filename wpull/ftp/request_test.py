import unittest
from wpull.body import Body
from wpull.ftp.request import Reply, Command, Request, Response


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
        reply = Reply(213, 'Hello world!\nFerret transfer protocol')
        self.assertEqual(
            b'213-Hello world!\r\n213 Ferret transfer protocol\r\n',
            reply.to_bytes()
        )
        self.assertEqual(213, reply.to_dict()['code'])
        self.assertEqual(
            'Hello world!\nFerret transfer protocol',
            reply.to_dict()['text']
        )
        self.assertEqual((2, 1, 3), reply.code_tuple())

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

    def test_to_dict(self):
        request = Request('ftp://foofle.com')
        request_dict = request.to_dict()

        self.assertEqual('ftp://foofle.com', request_dict['url'])
        self.assertEqual('ftp', request_dict['protocol'])

        response = Response()
        response.request = request
        response.reply = Reply(code=200, text='Success')
        response_dict = response.to_dict()

        self.assertEqual('ftp://foofle.com', response_dict['request']['url'])
        self.assertEqual('ftp', response_dict['protocol'])
        self.assertEqual(200, response_dict['reply']['code'])
        self.assertEqual(200, response_dict['response_code'])
        self.assertEqual('Success', response_dict['reply']['text'])
        self.assertEqual('Success', response_dict['response_message'])

    def test_to_dict_body(self):
        response = Response()
        response.body = Body()
        response_dict = response.to_dict()

        self.assertTrue(response_dict['body'])
        response.body.close()

        response = Response()
        response.body = NotImplemented
        response_dict = response.to_dict()

        self.assertFalse(response_dict['body'])
