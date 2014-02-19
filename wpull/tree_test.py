# encoding=utf-8
from wpull.backport.testing import unittest
from wpull.tree import TreeNode, TreeNodeError


class TestTree(unittest.TestCase):
    def test_two_node_relationship(self):
        parent_node = TreeNode()
        child_node = TreeNode()

        self.assertEqual(parent_node, parent_node.root)
        self.assertFalse(parent_node.parent)
        self.assertFalse(parent_node.children)

        parent_node.children.append(child_node)

        self.assertIn(child_node, parent_node.children)

        self.assertEqual(parent_node, child_node.parent)
        self.assertEqual(parent_node, child_node.root)

        self.assertRaises(
            TreeNodeError, parent_node.children.append, child_node)
        self.assertRaises(
            TreeNodeError, child_node.children.append, parent_node)
        self.assertRaises(
            TreeNodeError, parent_node.children.append, parent_node)
        self.assertRaises(
            TreeNodeError, child_node.children.append, child_node)
