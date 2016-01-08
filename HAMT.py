from hashlib import sha1
import os
from BinaryTree import BinaryTree
EmptyIndex = 2**64-1
DeletedMarker = 2**63
MinFileLength = 8+1+8*256 # 1 for type, 8 for length, 256 pointers
#header: 8 bytes size of file, 8 bytes size of deleted file
class HAMT:
	def __init__ (self,filename):
		self.filename = filename
		self.file = open(filename,"w+")
		self.delFile = DeletedFile("Del"+filename)
		self.WALfile = open("WAL"+filename,"w+")
		self.logReplay()
		self.WALfile.truncate(0)
		self.WALfile.seek(0)
		self.file.truncate(bytesToNumber(self.file.read(8)))
		self.delFile.file.truncate(bytesToNumber(self.file.read(8)))
		
	def __getitem__ (self,key):
		hasher = sha1()
		hasher.update(key)
		fileKey = hasher.digest()
		result = self.lookup(fileKey,16)
		if result is None:
			raise KeyError()
		return result

	def __setitem__(self,key,value):
		self.file.seek(0,os.SEEK_END)
		if self.file.tell() < MinFileLength:
			self.file.write(numberToBytes(0))
			self.file.write(numberToBytes(0))
			self.createInternal()
			self.logWrite(0,numberToBytes(self.file.tell()))
			self.logWrite(8,numberToBytes(0))
			self.logFlush()
			pos = self.file.tell()
			self.file.seek(0)
			self.file.write(numberToBytes(pos))
			self.file.write(numberToBytes(0))
		hasher = sha1()
		hasher.update(key)
		fileKey = hasher.digest()
		result = self.findAndInsert(fileKey,0,16,key,value)

	def __delitem__(self,key):
		hasher = sha1()
		hasher.update(key)
		fileKey = hasher.digest()
		self.skipHeader()
		result = self.deletionSearch(fileKey,0)

	def skipHeader(self):
		self.file.seek(16)

	def findAndInsert(self,fileKey,fileKeyByte,index,key,value):
		if index==EmptyIndex:
			return self.createNewLeaf(fileKey,key,value)
		self.file.seek(index,0)
		nodeType = self.file.read(1)
		if nodeType=='L':
			oldHash = self.file.read(20)
			oldLeafPosition = index
			newLeafPosition = self.createNewLeaf(fileKey,key,value)
			if oldHash == fileKey:
				return newLeafPosition
			return self.insert(oldHash[fileKeyByte:],oldLeafPosition,
							   fileKey[fileKeyByte:],newLeafPosition)		
		if nodeType=='I':
			newPosition = self.findAndInsert(
				fileKey,
				fileKeyByte+1,
				self.indexFromNode(index,ord(fileKey[fileKeyByte])),
				key,
				value)
			if newPosition:
				position = index+1+8*ord(fileKey[fileKeyByte])
				self.logWrite(position,numberToBytes(newPosition))
				self.logFlush()
				self.file.seek(position,0)			
				self.file.write(numberToBytes(newPosition))
		return None

	def logReplay(self):
		while True:
			pending = []
			while True:
				position = bytesToNumber(self.WALfile.read(8))
				if position == EmptyIndex:
					break
				length = bytesToNumber(self.WALfile.read(8))
				if length == 0:
					return
				data = bytesToNumber(self.WALfile.read(length))
				pending.append((postion,data))
			for positon,data in pending:
				if position > DeletedMarker:
					position-=DeletedMarker
					self.delFile.file.seek(position)
					self.delFile.file.write(data)
				else:
					self.file.seek(position)
					self.file.write(data)

	def logWrite(self,positon,data):
		self.WALfile.write(numberToBytes(positon))
		self.WALfile.write(numberToBytes(len(data)))
		self.WALfile.write(data)

	def delLogWrite(self,position,length):
		self.delFile.file.seek(0,os.SEEK_END)
		freeListLen = self.delFile.file.tell()
		self.logWrite(freeListLen+DeletedMarker,numberToBytes(position))
		self.logWrite(freeListLen+DeletedMarker+8,numberToBytes(length))
		self.delFile.addDeletedBlockToTrees(position,length)

	def logFlush(self):
		if self.WALfile.tell() >= 2**20:
			self.file.flush()
			os.fsync(self.file.fileno())
			self.WALfile.seek(0)
			self.WALfile.truncate(0)
		self.WALfile.write(numberToBytes(EmptyIndex))
		self.WALfile.flush()
		os.fsync(self.WALfile.fileno())

	def indexFromNode(self,index,byte):
		self.file.seek(index+8*byte+1,0)
		return bytesToNumber(self.file.read(8))

	def insert(self,oldHash,oldPosition,newHash,newPosition):
		if oldHash[0] == newHash[0]:
			newIndex = self.insert(oldHash[1:],oldPosition,
					   newHash[1:],newPosition)
			positions = [EmptyIndex for i in range(256)]
			positions[ord(oldHash[0])] = newIndex
		else:
			positions = [EmptyIndex for i in range(256)]
			positions[ord(oldHash[0])] = oldPosition
			positions[ord(newHash[0])] = newPosition
		return self.createInternal(positions)

	def createNewLeaf(self,fileKey,key,value):
		position = self.delFile.findDeletedBlockBySize(37+len(key)+len(value))
		print "pos ",position
		if position is None:
			self.file.seek(0,os.SEEK_END)
			position = self.file.tell()
		else:
			self.file.seek(position,os.SEEK_SET)
		self.logWrite(position,'L')
		self.logWrite(position+1,fileKey)
		self.logWrite(position+21,numberToBytes(len(key)))
		self.logWrite(position+29,numberToBytes(len(value)))
		self.logWrite(position+37,key)
		self.logWrite(position+37+len(key),value)
		self.logFlush()
		self.file.write('L')
		self.file.write(fileKey)
		self.file.write(numberToBytes(len(key)))
		self.file.write(numberToBytes(len(value)))
		self.file.write(key)
		self.file.write(value)
		return position

	def createInternal(self,positions=None):
		position = self.file.tell()
		self.logWrite(position,'I')
		if positions:
			for i in range(256):
				self.logWrite(position+1+i*8,numberToBytes(positions[i]))
		else:
			for i in range(256): 
				self.logWrite(position+1+i*8,numberToBytes(EmptyIndex))
		self.logFlush()
		self.file.write('I')
		if positions:
			for i in range(256):
				self.file.write(numberToBytes(positions[i]))
		else:
			for i in range(256): 
				self.file.write(numberToBytes(EmptyIndex))
		return position

	def deletionSearch(self,fileKey,index):
		nodeType = self.file.read(1)
		if nodeType == 'L':
			if self.file.read(20) == fileKey:
				keyLen = bytesToNumber(self.file.read(8))
				valLen = bytesToNumber(self.file.read(8))
				headerLen = 1+20+8+8
				length = headerLen+keyLen+valLen
				self.delLogWrite(self.file.tell()-headerLen,length)
				return length
		if nodeType =='I':
			position = self.file.tell()+ord(fileKey[index])*8
			self.file.seek(position)
			childPosition = bytesToNumber(self.file.read(8))
			if childPosition ==EmptyIndex:
				raise KeyError()
			self.file.seek(childPosition)
			length = self.deletionSearch(fileKey,index+1)
			if length:
				self.file.seek(position)
				self.logWrite(position,numberToBytes(EmptyIndex))
				self.logFlush()
				self.file.write(numberToBytes(EmptyIndex))
				self.delFile.file.write(numberToBytes(childPosition))
				self.delFile.file.write(numberToBytes(length))
		return False

	def lookup(self,key,index):
		if index==EmptyIndex:
			return None
		self.file.seek(index,0)
		nodeType = self.file.read(1)
		if nodeType=='L':
			result = self.readLeaf(index+1,key)
			if result:
				return result[2]
		if nodeType=='I':
			return self.lookup(key[1:],self.indexFromNode(index,ord(key[0])))
		return None

	def readLeaf(self,index,keyHash):
		self.file.seek(index,0)
		fileHash = self.file.read(20)
		if  keyHash and not fileHash.endswith(keyHash):
			return None
		fileKeyLen = self.file.read(8)
		fileValueLen = self.file.read(8)
		fileKeyLen = bytesToNumber(fileKeyLen)
		key = self.file.read(fileKeyLen)
		fileValueLen = bytesToNumber(fileValueLen)
		value = self.file.read(fileValueLen)
		return fileHash,key,value

	def dump(self,position=0,treeDepth=0):
		self.file.seek(position)
		if (position==0):
			position=16
			lengthOfFile = self.file.read(8)
			lengthOfDelFIle = self.file.read(8)
		nodeType = self.file.read(1) 
		if nodeType == 'L':
			keyHash,key,value = self.readLeaf(position+1,None)
			print "  "*treeDepth+'L: %s-->%s'%(key,value)
		elif nodeType == 'I':
			for i in range(256):
				index = self.file.read(8)
				newPosition = bytesToNumber(index)
				if newPosition == EmptyIndex:
					continue
				print "  "*treeDepth+'I: %s, %s'%(i,newPosition)
				saveToPosition = self.file.tell()
				self.dump(newPosition,treeDepth+1)
				self.file.seek(saveToPosition)
		else:
			print 'invalid nodeType: '+nodeType
class DeletedFile():
	def __init__(self,filename):
		self.file = open(filename,'w+')
		self.blocksBySize = BinaryTree()
		self.blocksByPosition = BinaryTree()
		self.blocksByIndex = dict()
		self.loadDeletedBlocks()
		self.maxIndex = -1

	def loadDeletedBlocks(self):
		index = 0
		while (True):
			posBytes = self.file.read(8)
			sizeBytes = self.file.read(8)
			if len(posBytes)!=8:
				break
			numSize = bytesToNumber(sizeBytes)
			numPos = bytesToNumber(posBytes)
			self.addDeletedBlockToTrees(numPos,numSize,index)
			index+=1

	def addDeletedBlockToTrees(self,numPos,numSize):
		self.file.seek(os.SEEK_END)
		index = self.file.tell()
		entry = DeletedFileEntry(numPos,numSize,index)
		self.blocksByPosition.insert(numPos,entry)
		self.blocksByIndex[index] = entry
		blocks = self.blocksBySize.find(numSize)
		if blocks:
			blocks.append(entry)
		else:
			self.blocksBySize.insert(numSize,[entry])
		if index>self.maxIndex:
			self.maxIndex = index

	def recoverBlock(self,entry):
		logWrite(8,numberToBytes(maxIndex)*16)
		if self.maxIndex == 0:
			self.maxIndex = -1
		else:
			replacement = self.blocksByIndex[maxIndex]
		del blocksByIndex[maxIndex]
		replacement.index = entry.index 
		maxIndex -=1
		self.file.seek(entry.index)
		self.file.write(replacement.positon)
		self.file.write(replacement.size)
		self.blocksByIndex[entry.index] = replacement
		self.blocksByPosition.remove(entry.position)
		positions = self.blocksBySize.find(entry.size)
		pos = positions.pop()
		if len(positions) == 0:
			self.blocksBySize.remove(entry.size) 
		return pos

	def findDeletedBlockBySize(self,size):
		result = self.blocksBySize.findNext(size)
		if not result:
			return None
		#import pdb;pdb.set_trace()
		foundSize,positions = result
		pos = positions.pop()
		if len(positions) == 0:
			self.blocksBySize.remove(foundSize)	
		self.blocksByPosition.remove(pos.pos)
		if foundSize == size:
			return pos.pos

class DeletedFileEntry():
	def __init__(self,pos,size,index): 
		'''postion = position in main file, size = entry, index = position in deleted file in bytes'''
		self.pos = pos
		self.size = size
		self.index = index

def bytesToNumber(bytes):
	total = 0
	for byte in bytes:
		total *= 256
		total += ord(byte)
	return total

def numberToBytes(number):
	bytes = [0,0,0,0,0,0,0,0]
	for i in range(len(bytes)):
		bytes[-i-1] = chr(number%256)
		number/=256
	return "".join(bytes)

if os.path.exists("HAMTfile"):
	os.unlink("HAMTfile")
if os.path.exists("WALHAMTfile"):
	os.unlink("WALHAMTfile")
if os.path.exists("DelHAMTfile"):
	os.unlink("DelHAMTfile")
h = HAMT("HAMTfile")
h['hello'] = 'a'
h['607'] = 'b'
h.dump()
print h['hello']
print h['607']
del h['hello']
try:
	print h['hello']
except KeyError:
	print "good"
try:
	del h['hello']
except KeyError:
	print "deleted"
h['foo'] = 'bar'
h.dump()
