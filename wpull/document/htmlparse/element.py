'''HTML tree things.'''
import collections


Element = collections.namedtuple(
    'ElementType',
    ['tag', 'attrib', 'text', 'tail', 'end']
    )
'''An HTML element.

Attributes
    tag (str): The tag name of the element.
    attrib (dict): The attributes of the element.
    text (str, None): The text of the element.
    tail (str, None): The text after the element.
    end (bool): Whether the tag is and end tag.
'''

Doctype = collections.namedtuple(
    'DoctypeType',
    ['text']
    )
'''A Doctype.

Attributes:
    text (str): The Doctype text.
'''

Comment = collections.namedtuple(
    'CommentType',
    ['text']
    )
'''A comment.

Attributes:
    text (str): The comment text.
'''
