# encoding=utf-8

import copy
import unittest

from wpull.collections import LinkedList, OrderedDefaultDict


class TestCollections(unittest.TestCase):
    def test_ordered_default_dict(self):
        mapping = OrderedDefaultDict(lambda: 2)
        mapping['a'] += 4
        mapping['b'] += 3
        mapping['c'] += 2

        self.assertEqual(
            [('a', 6), ('b', 5), ('c', 4)],
            list(mapping.items())
        )
        d1 = OrderedDefaultDict()
        d1['a'] = object()
        d2 = copy.deepcopy(d1)
        self.assertNotEqual(d1['a'], d2['a'])

    def test_linked_list(self):
        linked_list = LinkedList()

        for dummy in range(2):
            self.assertEqual(0, len(linked_list))

            linked_list.append('a')

            self.assertEqual(1, len(linked_list))

            self.assertEqual('a', linked_list.head.value)
            self.assertEqual('a', linked_list.tail.value)

            linked_list.append('b')

            self.assertEqual(2, len(linked_list))

            self.assertEqual('a', linked_list.head.value)
            self.assertEqual('b', linked_list.tail.value)

            linked_list.append('c')

            self.assertEqual(3, len(linked_list))
            self.assertEqual(('a', 'b', 'c'), tuple(linked_list))

            self.assertEqual('a', linked_list.head.value)
            self.assertEqual('c', linked_list.tail.value)

            self.assertEqual('a', linked_list[0])
            self.assertEqual('b', linked_list[1])
            self.assertEqual('c', linked_list[2])

            linked_list.appendleft('d')

            self.assertEqual(4, len(linked_list))
            self.assertEqual(('d', 'a', 'b', 'c'), tuple(linked_list))

            self.assertEqual('d', linked_list.head.value)
            self.assertEqual('c', linked_list.tail.value)

            linked_list.remove('a')

            self.assertEqual(3, len(linked_list))
            self.assertEqual(('d', 'b', 'c'), tuple(linked_list))

            self.assertEqual('d', linked_list.head.value)
            self.assertEqual('c', linked_list.tail.value)

            linked_list.append('a')

            self.assertEqual(4, len(linked_list))
            self.assertEqual(('d', 'b', 'c', 'a'), tuple(linked_list))

            self.assertEqual('d', linked_list.head.value)
            self.assertEqual('a', linked_list.tail.value)

            linked_list.remove('d')

            self.assertEqual(3, len(linked_list))
            self.assertEqual(('b', 'c', 'a'), tuple(linked_list))

            self.assertEqual('b', linked_list.head.value)
            self.assertEqual('a', linked_list.tail.value)

            linked_list.remove('a')

            self.assertEqual(2, len(linked_list))
            self.assertEqual(('b', 'c'), tuple(linked_list))

            self.assertEqual('b', linked_list.head.value)
            self.assertEqual('c', linked_list.tail.value)

            linked_list.remove('b')

            self.assertEqual(1, len(linked_list))
            self.assertEqual(('c',), tuple(linked_list))

            self.assertEqual('c', linked_list.head.value)
            self.assertEqual('c', linked_list.tail.value)

            linked_list.remove('c')

            self.assertEqual(0, len(linked_list))
            self.assertEqual((), tuple(linked_list))

            self.assertRaises(ValueError, linked_list.remove, 'asdf')

            linked_list.appendleft('a')
            linked_list.append('b')
            linked_list.appendleft('c')
            linked_list.append('d')

            self.assertEqual(4, len(linked_list))
            self.assertEqual(('c', 'a', 'b', 'd'), tuple(linked_list))

            self.assertEqual('c', linked_list.popleft())
            self.assertEqual('d', linked_list.pop())

            self.assertEqual(2, len(linked_list))
            self.assertEqual(('a', 'b'), tuple(linked_list))

            linked_list.clear()
