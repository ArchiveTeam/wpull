# encoding-utf8
'''Tree data structure.'''
import collections


class TreeNodeError(Exception):
    pass


class ChildList(collections.MutableSequence):
    def __init__(self, parent_tree_node):
        self._parent = parent_tree_node
        self._list = []

    def __getitem__(self, index):
        return self._list[index]

    def __setitem__(self, index, node):
        if self._list[index] != node:
            self._accept_child(node)
            self._list[index] = node

    def __delitem__(self, index):
        node = self._list[index]

        node.make_orphan()

        del self._list[index]

    def __len__(self):
        return len(self._list)

    def insert(self, index, node):
        self._accept_child(node)
        self._list.insert(index, node)

    def _accept_child(self, node):
        if node in self._list:
            raise TreeNodeError('Tree Node already a child of this parent.')

        if node.parent:
            raise TreeNodeError('Tree Node already has a parent.')

        if self._parent.root == node.root:
            raise TreeNodeError('Tree Node already in tree.')

        node.make_child(self._parent)

    def __str__(self):
        return '[{0}]'.format(','.join([str(item) for item in self._list]))


class TreeNode(object):
    '''Tree Node.'''
    def __init__(self):
        self._root = self
        self._parent = None
        self._children = ChildList(self)

    @property
    def root(self):
        return self._root

    @property
    def parent(self):
        return self._parent

    @property
    def siblings(self):
        if self._parent:
            return self._parent.children
        else:
            return ()

    @property
    def previous_sibling(self):
        if self._parent:
            index = self._parent.children.index(self)

            if index > 0:
                return self._parent.children[index - 1]

    @property
    def next_sibling(self):
        if self._parent:
            index = self._parent.children.index(self)

            try:
                return self._parent.children[index + 1]
            except IndexError:
                pass

    @property
    def children(self):
        return self._children

    def make_orphan(self):
        if self._parent:
            self._parent.children.remove(self)

        self._parent = None
        self._root = self

    def make_child(self, parent):
        self._parent = parent
        self._root = parent.root
