# encoding=utf-8
'''Data structures.'''
from collections import OrderedDict
import collections
import copy
import itertools
import functools


class OrderedDefaultDict(OrderedDict):
    '''An ordered default dict.

    http://stackoverflow.com/a/6190500/1524507
    '''
    def __init__(self, default_factory=None, *args, **kwargs):
        if default_factory is not None and \
           not isinstance(default_factory, collections.Callable):
            raise TypeError('First argument must be callable')
        OrderedDict.__init__(self, *args, **kwargs)
        self.default_factory = default_factory

    def __getitem__(self, key):
        try:
            return OrderedDict.__getitem__(self, key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value

    def __reduce__(self):
        if self.default_factory is None:
            args = tuple()
        else:
            args = self.default_factory,
        return type(self), args, None, None, self.items()

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        return type(self)(self.default_factory, self)

    def __deepcopy__(self, memo):
        return type(self)(self.default_factory,
                          copy.deepcopy(tuple(self.items())))

    def __repr__(self):
        return 'OrderedDefaultDict(%s, %s)' % (
            self.default_factory, collections.OrderedDict.__repr__(self))


class LinkedListNode(object):
    '''A node in a :class:`LinkedList`.

    Attributes:
        value: Any value.
        head (LinkedListNode): The node in front.
        tail (LinkedListNode): The node in back.
    '''
    __slots__ = ('value', 'head', 'tail')

    def __init__(self, value, head=None, tail=None):
        self.value = value
        self.head = head
        self.tail = tail

    def link_head(self, node):
        '''Add a node to the head. '''
        assert not node.tail
        old_head = self.head

        if old_head:
            assert old_head.tail == self
            old_head.tail = node
            node.head = old_head

        node.tail = self
        self.head = node

    def link_tail(self, node):
        '''Add a node to the tail.'''
        assert not node.head
        old_tail = self.tail

        if old_tail:
            assert old_tail.head == self
            old_tail.head = node
            node.tail = old_tail

        node.head = self
        self.tail = node

    def unlink(self):
        '''Remove this node and link any head or tail.'''
        old_head = self.head
        old_tail = self.tail

        self.head = None
        self.tail = None

        if old_head:
            old_head.tail = old_tail

        if old_tail:
            old_tail.head = old_head


class LinkedList(object):
    '''Doubly linked list.

    Attributes:
        map (dict): A mapping of values to nodes.
        head (:class:`LinkedListNode`): The first node.
        tail (:class:`LinkedListNode`): The last node.
    '''
    def __init__(self):
        self.map = {}
        self.head = None
        self.tail = None

    def __contains__(self, value):
        return value in self.map

    def __iter__(self):
        current_node = self.head
        while True:
            if not current_node:
                break

            yield current_node.value

            current_node = current_node.tail

    def __reversed__(self):
        return reversed(self)

    def __len__(self):
        return len(self.map)

    def index(self, value):
        for test_value, count in zip(self, itertools.count()):
            if test_value == value:
                return count

        raise IndexError()

    def __getitem__(self, key):
        if not self.map:
            raise IndexError('List is empty.')

        if key == 0:
            return self.head.value
        elif key == len(self.map) - 1:
            return self.tail.value

        for value, count in zip(self, itertools.count()):
            if count == key:
                return value

        raise IndexError('Value not in list.')

    def append(self, value):
        if value in self.map:
            raise ValueError('Linked list can only contain one of value.')

        node = LinkedListNode(value)
        self.map[value] = node

        if self.tail:
            self.tail.link_tail(node)

        self.tail = node

        if not self.head:
            self.head = node

    def appendleft(self, value):
        if value in self.map:
            raise ValueError('Linked list can only contain one of value.')

        node = LinkedListNode(value)
        self.map[value] = node

        if self.head:
            self.head.link_head(node)

        self.head = node

        if not self.tail:
            self.tail = node

    def remove_node(self, node):
        if self.head == node:
            self.head = self.head.tail

        if self.tail == node:
            self.tail = self.tail.head

        node.unlink()

    def remove(self, value):
        try:
            node = self.map[value]
        except KeyError:
            raise ValueError('Value not in list.')

        del self.map[value]
        self.remove_node(node)

    def pop(self):
        if not self.map:
            raise IndexError('List is empty.')

        value = self.tail.value

        self.remove_node(self.tail)
        del self.map[value]
        return value

    def popleft(self):
        if not self.map:
            raise IndexError('List is empty.')

        value = self.head.value

        self.remove_node(self.head)
        del self.map[value]
        return value

    def clear(self):
        self.map = {}
        self.head = None
        self.tail = None


class FrozenDict(collections.Mapping, collections.Hashable):
    '''Immutable mapping wrapper.'''
    __slots__ = ('orig_dict', 'hash_cache',)

    def __init__(self, orig_dict):
        self.orig_dict = orig_dict
        self.hash_cache = hash(tuple(sorted(self.orig_dict.items())))

    def __len__(self):
        return len(self.orig_dict)

    def __iter__(self):
        return iter(self.orig_dict)

    def __getitem__(self, key):
        return self.orig_dict[key]

    def __hash__(self):
        return self.hash_cache


EmptyFrozenDict = functools.partial(FrozenDict, {})
