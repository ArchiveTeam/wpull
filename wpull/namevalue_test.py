# encoding=utf-8
from wpull.backport.testing import unittest
from wpull.namevalue import guess_line_ending, unfold_lines, NameValueRecord


class TestNameValue(unittest.TestCase):
    RECORD_STR_1 = ('entry:\r\n'
        'who:   Gilbert, W.S. | Sullivan, Arthur\r\n'
        'what:  The Yeomen of\r\n'
        '       the Guard\r\n'
        'when/created:  1888\r\n')
    RECORD_STR_2 = ('entry:\n'
        'who:   Gilbert, W.S. | Sullivan, Arthur\n'
        'what:  The Yeomen of\n'
        '       the Guard\n'
        'when/created:  1888\n')
    RECORD_STR_3 = ('entry:\r\n'
        'who:   Gilbert, W.S. | Sullivan, Arthur\r\n'
        'what:  The Yeomen of the Guard\r\n'
        'when/created:  1888\r\n')

    def test_guess_line_ending(self):
        self.assertEqual('\r\n', guess_line_ending(self.RECORD_STR_1))
        self.assertEqual('\n', guess_line_ending(self.RECORD_STR_2))

    def test_unfold_lines(self):
        self.assertEqual(self.RECORD_STR_3, unfold_lines(self.RECORD_STR_1))

    def test_name_value_record_setters(self):
        record = NameValueRecord()

        self.assertNotIn('cache', record)
        self.assertRaises(KeyError, lambda: record['cache'])
        record['cache'] = 'value1'
        self.assertEqual('value1', record['CACHE'])
        self.assertEqual(['value1'], record.get_list('Cache'))
        self.assertEqual(
            [('Cache', 'value1')],
            list(record.get_all())
        )

    def test_name_value_record_parsing(self):
        record = NameValueRecord()
        record.parse(self.RECORD_STR_1)
        self.assertIn('who', record)
        self.assertEqual('Gilbert, W.S. | Sullivan, Arthur', record['who'])

    def test_name_value_str_format(self):
        record = NameValueRecord()
        record.parse(self.RECORD_STR_1)
        self.assertEqual(
            ('Entry:\r\n'
            'Who: Gilbert, W.S. | Sullivan, Arthur\r\n'
            'What: The Yeomen of the Guard\r\n'
            'When/Created: 1888\r\n'),
            str(record)
        )

    def test_name_value_utf8(self):
        text = '''Name: dogé'''
        record = NameValueRecord()
        record.parse(text)

        self.assertEqual('dogé', record['name'])

    def test_name_value_fallback(self):
        text = '''Name: Кракозябры'''.encode('koi8-r')
        record = NameValueRecord()
        record.parse(text)

        self.assertEqual(
            'Кракозябры'.encode('koi8-r').decode('latin1'),
            record['name'])

    def test_missing_colon(self):
        record = NameValueRecord()

        self.assertRaises(ValueError, record.parse, 'text:hello\nhi\n')

        record = NameValueRecord()

        record.parse('text:hello\nhi\n', strict=False)

        self.assertEqual('hello', record['text'])
        self.assertNotIn('hi', record)
