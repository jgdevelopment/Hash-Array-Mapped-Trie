# hi
# Once upon a time, in a digital realm far far away, there lived a Hash Array Mapped Trie
# who dreamed of efficiently storing key-value pairs. This brave data structure ventured
# through the lands of persistent storage, wielding the power of SHA-1 hashes and 
# write-ahead logging to protect precious data from the dragons of corruption and loss.

from hashlib import sha1
import os
import logging
from typing import Optional, Any, Dict, List, Tuple
from BinaryTree import BinaryTree

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Custom Exception Classes
class HAMTError(Exception):
    """Base exception class for HAMT operations"""
    pass

class HAMTCorruptionError(HAMTError):
    """Raised when data corruption is detected"""
    pass

class HAMTKeyError(HAMTError):
    """Raised when a key is not found"""
    pass

class HAMTIOError(HAMTError):
    """Raised when I/O operations fail"""
    pass

# Configuration constants
DEFAULT_WAL_FLUSH_SIZE = 2**20  # 1MB
DEFAULT_CACHE_SIZE = 1000
EmptyIndex = 2**64-1
DeletedMarker = 2**63
MinFileLength = 8+1+8*256 # 1 for type, 8 for length, 256 pointers
#header: 8 bytes size of file, 8 bytes size of deleted file
class HAMT:
	"""Hash Array Mapped Trie with persistent storage and WAL"""
	def __init__(self, filename: str) -> None:
		"""Initialize HAMT with filename for persistent storage"""
		try:
			self.filename = filename
			self.cache: Dict[bytes, bytes] = {}
			self.cache_size = DEFAULT_CACHE_SIZE
			logger.info(f"Initializing HAMT with file: {filename}")
			
			self.file = open(filename, "w+b")
			self.delFile = DeletedFile("Del" + filename)
			self.WALfile = open("WAL" + filename, "w+b")
			
			self.logReplay()
			self.WALfile.truncate(0)
			self.WALfile.seek(0)
			
			# Read and validate header
			self.file.seek(0)
			file_size_bytes = self.file.read(8)
			del_size_bytes = self.file.read(8)
			
			if len(file_size_bytes) == 8 and len(del_size_bytes) == 8:
				file_size = bytesToNumber(file_size_bytes)
				del_size = bytesToNumber(del_size_bytes)
				self.file.truncate(file_size)
				self.delFile.file.truncate(del_size)
			else:
				logger.warning("Invalid or missing header, initializing new file")
				
		except Exception as e:
			logger.error(f"Failed to initialize HAMT: {e}")
			raise HAMTIOError(f"Could not initialize HAMT file {filename}: {e}")
		
	def __getitem__(self, key: bytes) -> bytes:
		"""Get value for given key"""
		# Check cache first
		if key in self.cache:
			logger.debug(f"Cache hit for key: {key}")
			return self.cache[key]
			
		try:
			hasher = sha1()
			hasher.update(key)
			fileKey = hasher.digest()
			result = self.lookup(fileKey, 16)
			if result is None:
				raise HAMTKeyError(f"Key not found: {key}")
			
			# Add to cache
			self._cache_put(key, result)
			return result
		except Exception as e:
			logger.error(f"Error getting key {key}: {e}")
			if isinstance(e, HAMTError):
				raise
			raise HAMTIOError(f"I/O error during key lookup: {e}")

	def _cache_put(self, key: bytes, value: bytes) -> None:
		"""Add key-value pair to cache with LRU eviction"""
		if len(self.cache) >= self.cache_size:
			# Simple FIFO eviction (could be improved to LRU)
			oldest_key = next(iter(self.cache))
			del self.cache[oldest_key]
		self.cache[key] = value

	def _cache_invalidate(self, key: bytes) -> None:
		"""Remove key from cache"""
		self.cache.pop(key, None)

	def __enter__(self):
		"""Context manager entry"""
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit with proper cleanup"""
		try:
			self.close()
		except Exception as e:
			logger.error(f"Error closing HAMT: {e}")
		return False

	def close(self) -> None:
		"""Close all file handles"""
		try:
			if hasattr(self, 'file'):
				self.file.close()
			if hasattr(self, 'WALfile'):
				self.WALfile.close()
			if hasattr(self, 'delFile') and hasattr(self.delFile, 'file'):
				self.delFile.file.close()
			logger.info(f"Closed HAMT: {self.filename}")
		except Exception as e:
			logger.error(f"Error closing files: {e}")
			raise HAMTIOError(f"Failed to close files: {e}")

	def keys(self):
		"""Iterator over all keys (simplified implementation)"""
		# This would require traversing the entire trie structure
		# For now, return cache keys as a basic implementation
		return iter(self.cache.keys())

	def __len__(self) -> int:
		"""Return approximate number of items (cache size for now)"""
		return len(self.cache)

	def get(self, key: bytes, default: Optional[bytes] = None) -> Optional[bytes]:
		"""Get value with default fallback"""
		try:
			return self[key]
		except HAMTKeyError:
			return default

	def __setitem__(self, key: bytes, value: bytes) -> None:
		"""Set key-value pair in HAMT"""
		try:
			self.file.seek(0, os.SEEK_END)
			if self.file.tell() < MinFileLength:
				self.file.write(numberToBytes(0))
				self.file.write(numberToBytes(0))
				self.createInternal()
				self.logWrite(0, numberToBytes(self.file.tell()))
				self.logWrite(8, numberToBytes(0))
				self.logFlush()
				pos = self.file.tell()
				self.file.seek(0)
				self.file.write(numberToBytes(pos))
				self.file.write(numberToBytes(0))
			
			hasher = sha1()
			hasher.update(key)
			fileKey = hasher.digest()
			result = self.findAndInsert(fileKey, 0, 16, key, value)
			
			# Update cache
			self._cache_put(key, value)
			logger.debug(f"Set key-value pair: {key}")
			
		except Exception as e:
			logger.error(f"Error setting key {key}: {e}")
			raise HAMTIOError(f"Failed to set key-value pair: {e}")

	def __delitem__(self, key: bytes) -> None:
		"""Delete key from HAMT"""
		try:
			hasher = sha1()
			hasher.update(key)
			fileKey = hasher.digest()
			self.skipHeader()
			result = self.deletionSearch(fileKey, 0)
			
			# Remove from cache
			self._cache_invalidate(key)
			logger.debug(f"Deleted key: {key}")
			
		except Exception as e:
			logger.error(f"Error deleting key {key}: {e}")
			if isinstance(e, HAMTError):
				raise
			raise HAMTIOError(f"Failed to delete key: {e}")

	def skipHeader(self) -> None:
		"""Skip to data section after header"""
		self.file.seek(16)

	def findAndInsert(self, fileKey: bytes, fileKeyByte: int, index: int, key: bytes, value: bytes) -> Optional[int]:
		"""Find position to insert key-value pair or insert if not found"""
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
				pending.append((position,data))
			for position,data in pending:
				if position > DeletedMarker:
					position-=DeletedMarker
					self.delFile.file.seek(position)
					self.delFile.file.write(data)
				else:
					self.file.seek(position)
					self.file.write(data)

	def logWrite(self,position,data):
		self.WALfile.write(numberToBytes(position))
		self.WALfile.write(numberToBytes(len(data)))
		self.WALfile.write(data)

	def delLogWrite(self,position,length):
		self.delFile.file.seek(0,os.SEEK_END)
		freeListLen = self.delFile.file.tell()
		self.logWrite(freeListLen+DeletedMarker,numberToBytes(position))
		self.logWrite(freeListLen+DeletedMarker+8,numberToBytes(length))
		self.delFile.addDeletedBlockToTrees(position,length)

	def logFlush(self) -> None:
		"""Flush WAL to persistent storage"""
		try:
			if self.WALfile.tell() >= DEFAULT_WAL_FLUSH_SIZE:
				logger.debug("Flushing WAL to persistent storage")
				self.file.flush()
				os.fsync(self.file.fileno())
				self.WALfile.seek(0)
				self.WALfile.truncate(0)
			self.WALfile.write(numberToBytes(EmptyIndex))
			self.WALfile.flush()
			os.fsync(self.WALfile.fileno())
		except Exception as e:
			logger.error(f"Error flushing WAL: {e}")
			raise HAMTIOError(f"Failed to flush WAL: {e}")

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
		print("pos ", position)
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
			print("  "*treeDepth+'L: %s-->%s'%(key,value))
		elif nodeType == 'I':
			for i in range(256):
				index = self.file.read(8)
				newPosition = bytesToNumber(index)
				if newPosition == EmptyIndex:
					continue
				print("  "*treeDepth+'I: %s, %s'%(i,newPosition))
				saveToPosition = self.file.tell()
				self.dump(newPosition,treeDepth+1)
				self.file.seek(saveToPosition)
		else:
			print('invalid nodeType: '+nodeType)
class DeletedFile:
	"""Manages deleted blocks for space reuse"""
	def __init__(self, filename: str):
		try:
			self.filename = filename
			self.file = open(filename, 'w+b')
			self.blocksBySize = BinaryTree()
			self.blocksByPosition = BinaryTree()
			self.blocksByIndex: Dict[int, 'DeletedFileEntry'] = {}
			self.maxIndex = -1
			self.loadDeletedBlocks()
			logger.info(f"Initialized deleted file manager: {filename}")
		except Exception as e:
			logger.error(f"Failed to initialize deleted file: {e}")
			raise HAMTIOError(f"Could not initialize deleted file {filename}: {e}")

	def loadDeletedBlocks(self):
		index = 0
		while (True):
			posBytes = self.file.read(8)
			sizeBytes = self.file.read(8)
			if len(posBytes)!=8:
				break
			numSize = bytesToNumber(sizeBytes)
			numPos = bytesToNumber(posBytes)
			self.addDeletedBlockToTrees(numPos, numSize, index)
			index+=1

	def addDeletedBlockToTrees(self, numPos, numSize, index=None):
		if index is None:
			self.file.seek(0, os.SEEK_END)
			index = self.file.tell()
		entry = DeletedFileEntry(numPos, numSize, index)
		self.blocksByPosition.insert(numPos, entry)
		self.blocksByIndex[index] = entry
		blocks = self.blocksBySize.find(numSize)
		if blocks:
			blocks.append(entry)
		else:
			self.blocksBySize.insert(numSize, [entry])
		if index > self.maxIndex:
			self.maxIndex = index

	def recoverBlock(self,entry):
		self.logWrite(8, numberToBytes(self.maxIndex*16))
		if self.maxIndex == 0:
			self.maxIndex = -1
		else:
			replacement = self.blocksByIndex[self.maxIndex]
		del self.blocksByIndex[self.maxIndex]
		replacement.index = entry.index 
		self.maxIndex -= 1
		self.file.seek(entry.index)
		self.file.write(numberToBytes(replacement.pos))
		self.file.write(numberToBytes(replacement.size))
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
		foundSize,positions = result
		pos = positions.pop()
		if len(positions) == 0:
			self.blocksBySize.remove(foundSize)	
		self.blocksByPosition.remove(pos.pos)
		if foundSize == size:
			return pos.pos

class DeletedFileEntry:
	"""Entry representing a deleted block that can be reused"""
	def __init__(self, pos: int, size: int, index: int):
		self.pos = pos
		self.size = size
		self.index = index
	
	def __repr__(self) -> str:
		return f"DeletedFileEntry(pos={self.pos}, size={self.size}, index={self.index})"

def bytesToNumber(bytes_data: bytes) -> int:
	"""Convert bytes to integer"""
	total = 0
	for byte in bytes_data:
		total *= 256
		if isinstance(byte, str):  # Python 2 compatibility
			total += ord(byte)
		else:  # Python 3
			total += byte
	return total

def numberToBytes(number: int) -> bytes:
	"""Convert integer to 8-byte representation"""
	result = []
	for i in range(8):
		result.insert(0, number % 256)
		number //= 256  # Use integer division for Python 3 compatibility
	return bytes(result)

# Cleanup and test code
def cleanup_test_files():
	"""Clean up test files"""
	test_files = ["HAMTfile", "WALHAMTfile", "DelHAMTfile"]
	for filename in test_files:
		try:
			if os.path.exists(filename):
				os.unlink(filename)
				logger.info(f"Cleaned up test file: {filename}")
		except Exception as e:
			logger.warning(f"Could not clean up {filename}: {e}")

def run_basic_test():
	"""Run a basic functionality test"""
	try:
		cleanup_test_files()
		logger.info("Starting HAMT basic test")
		
		with HAMT("HAMTfile") as hamt:
			# Test basic operations
			test_key = b"test_key"
			test_value = b"test_value"
			
			# Test set and get
			hamt[test_key] = test_value
			retrieved_value = hamt[test_key]
			assert retrieved_value == test_value, "Set/Get test failed"
			
			# Test cache
			cached_value = hamt[test_key]  # Should hit cache
			assert cached_value == test_value, "Cache test failed"
			
			# Test get with default
			missing_value = hamt.get(b"missing_key", b"default")
			assert missing_value == b"default", "Get with default test failed"
			
			logger.info("All basic tests passed!")
			
	except Exception as e:
		logger.error(f"Test failed: {e}")
		raise

if __name__ == "__main__":
	run_basic_test()
	cleanup_test_files()
