from random import random
from time import time
class BinaryTree(object):
	def __init__(self):
		self.root = None
	def find(self, needle):
		if self.root:
			return self.root.find(needle)
		else:
			return None
	def insert (self, insertKey, insertValue):
		if self.root:
			self.root.insert(insertKey,insertValue)
		else:
			self.root = Node(insertKey,insertValue)
	def printOut(self):
		if self.root:
			self.root.printOut()
		else:
			print "empty"
	def findNext(self, needle):
		if self.root:
			return self.root.findNext(needle)
		else:
			return None
	def findPrev(self, needle):
		if self.root:
			return self.root.findPrev(needle)
		else:
			return None	
	def remove(self, needle):
		if self.root:
			self.root.remove(None,needle)
			if self.root.key == needle:
				self.root = self.root.right
		else:
			return None
	def check(self):
		if self.root is None:
			return True
		self.root.check(None,None)
class Node(object):
	def __init__(self, key, value):
		self.value = value
		self.key = key
		self.left = None
		self.right = None

	def check(self,maxV,minV):
		if self.left:
			if maxV is not None and self.left.value>maxV:
				return False
			maxV = self.value
			self.left.check(maxV,minV)
		if self.right:
			if minV is not None and self.right.value<minV:
				return False
			minV = self.value
			self.right.check(maxV,minV)
		return True

	def insert(self, insertKey, insertValue):
		if insertKey>self.key:
			if self.right:
				self.right.insert(insertKey,insertValue)
			else:
				self.right = Node(insertKey,insertValue)
		elif insertKey < self.key:
			if self.left:
				self.left.insert(insertKey,insertValue)
			else:
				self.left = Node(insertKey,insertValue)
		else:
			self.value = insertValue
	def find(self, needle):
		if needle == self.key:
			return self.value
		if needle > self.key:
			if self.right:
				return self.right.find(needle)
		else:
			if self.left:
				return self.left.find(needle)
	def findNext(self, needle):
		if needle == self.key:
			return self.key,self.value
		if needle > self.key:
			if self.right:
				return self.right.findNext(needle)
		else:
			if self.left:
				result = self.left.findNext(needle)
				if result is None:
					return self.key,self.value
				return result
			else:
				return self.key, self.value
	def findPrev(self, needle):
		if needle == self.key:
			return self.key,self.value
		if needle < self.key:
			if self.left:
				return self.left.findPrev(needle)
		else:
			if self.right:
				result = self.right.findPrev(needle)
				if result is None:
					return self.key,self.value
				return result
			else:
				return self.key, self.value
	def printOut(self, depth = 0, prefix=''):
		print ' '*(depth *2),
		print prefix, 
		print self.value,
		print self.key
		if self.left:
			self.left.printOut(depth+1,"Left: ")
		if self.right:
			self.right.printOut(depth+1, "Right: ")
	def height(self):
		leftHeight = 0
		rightHeight = 0
		if self.right is not None:
			rightHeight = self.right.height()		
		if self.left is not None:
			leftHeight = self.left.height()		
		return max(leftHeight,rightHeight)+1
	def remove(self, parent, needle):
		if needle == self.key: #fix remove root
			currentNode = self.right
			leftParent = self
			while currentNode:
				leftParent = currentNode
				currentNode = currentNode.left
			leftParent.left = self.left
			if parent:
				if parent.left == self:
					parent.left = self.right
				else:
					parent.right = self.right
		else:
			if needle<self.key:
				if not self.left:
					raise IndexError("couldnt find "+str(needle))
				self.left.remove(self,needle)
			else:
				if not self.right:
					raise IndexError("couldnt find "+str(needle))
				self.right.remove(self,needle)

# def benchmark(func,*args):
# 	start = time()
# 	x =0
# 	while time()-start<1:
# 		x+=1
# 		func(*args)
# 	return x
# Test
numbers = []
for x in range(10):
	numbers.append(random())
tree = BinaryTree()
for number in numbers:
	tree.insert(number,number+1)
numbers.sort()
tree.printOut()
for i,number in enumerate(numbers):
 	tree.remove(number)
 	tree.check()
print "items removed"
tree.printOut()
####
# for i,number in enumerate(numbers):
# 	assert (number,number+1)==tree.findNext(number)
# 	#import pdb; pdb.set_trace()
# 	if i<len(numbers)-1:
# 		assert (numbers[i+1],numbers[i+1]+1)==tree.findNext(number+0.00000000001)
# 	else:
# 		assert None==tree.findNext(number+0.00000000001)
# 	if i==0:
# 		assert None==tree.findPrev(number-0.00000000001)
# 	else:
# 		assert (numbers[i-1],numbers[i-1]+1)==tree.findPrev(number-0.00000000001) 
# for i,number in enumerate(numbers):
# 	tree.remove(number)
# for number in numbers:
# 	if not tree.find(number):
# 		print "not found"
# if tree.find(2):
# 	print "ERROR"
#tree.insert(7)
#tree.insert(5)
# #tree.insert(4)
# #tree.insert(2)
# #node = Node(2)
# #print node.height()
# #node.printOut()
# print benchmark(tree.find, 3)
# print benchmark(tree.findTwo, 3)