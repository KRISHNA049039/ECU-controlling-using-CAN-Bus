"""
Message Queue Service

Thread-safe message queue for passing decoded messages between services.
"""
import queue
import logging
from typing import Any, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Generic message container"""
    message_type: str  # 'can_frame', 'telemetry', 'dtc', 'uds', etc.
    payload: Dict[str, Any]
    timestamp: float
    source: str  # Service that created the message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "message_type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "source": self.source
        }


class MessageQueue:
    """Thread-safe message queue for inter-service communication"""
    
    def __init__(self, max_size: int = 1000, name: str = "default"):
        """
        Initialize message queue
        
        Args:
            max_size: Maximum queue size
            name: Queue name for logging
        """
        self.name = name
        self.max_size = max_size
        self._queue = queue.Queue(maxsize=max_size)
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._total_dropped = 0
        self._lock = threading.Lock()
        
        logger.info(f"Initialized message queue '{name}' with max size {max_size}")
    
    def enqueue(self, message: Message, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Add message to queue
        
        Args:
            message: Message to enqueue
            block: Whether to block if queue is full
            timeout: Timeout in seconds (None = wait forever if block=True)
            
        Returns:
            True if message was enqueued, False otherwise
        """
        try:
            self._queue.put(message, block=block, timeout=timeout)
            with self._lock:
                self._total_enqueued += 1
            logger.debug(f"Enqueued {message.message_type} message to '{self.name}'")
            return True
        except queue.Full:
            with self._lock:
                self._total_dropped += 1
            logger.warning(
                f"Queue '{self.name}' is full, dropped {message.message_type} message"
            )
            return False
        except Exception as e:
            logger.error(f"Error enqueueing message to '{self.name}': {e}")
            return False
    
    def dequeue(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Message]:
        """
        Remove and return message from queue
        
        Args:
            block: Whether to block if queue is empty
            timeout: Timeout in seconds (None = wait forever if block=True)
            
        Returns:
            Message if available, None otherwise
        """
        try:
            message = self._queue.get(block=block, timeout=timeout)
            with self._lock:
                self._total_dequeued += 1
            logger.debug(f"Dequeued {message.message_type} message from '{self.name}'")
            return message
        except queue.Empty:
            return None
        except Exception as e:
            logger.error(f"Error dequeuing message from '{self.name}': {e}")
            return None
    
    def dequeue_batch(self, max_count: int = 100, timeout: float = 1.0) -> list[Message]:
        """
        Dequeue multiple messages
        
        Args:
            max_count: Maximum number of messages to dequeue
            timeout: Total timeout in seconds
            
        Returns:
            List of messages
        """
        messages = []
        remaining_timeout = timeout
        
        while len(messages) < max_count and remaining_timeout > 0:
            try:
                # Use short timeout for each get
                msg = self.dequeue(block=True, timeout=min(0.1, remaining_timeout))
                if msg:
                    messages.append(msg)
                remaining_timeout -= 0.1
            except Exception:
                break
        
        return messages
    
    def peek(self) -> Optional[Message]:
        """
        View next message without removing it
        
        Returns:
            Next message if available, None otherwise
        """
        try:
            # Get message and put it back
            message = self._queue.get(block=False)
            self._queue.put(message, block=False)
            return message
        except (queue.Empty, queue.Full):
            return None
    
    def size(self) -> int:
        """Get current queue size"""
        return self._queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self._queue.empty()
    
    def is_full(self) -> bool:
        """Check if queue is full"""
        return self._queue.full()
    
    def clear(self) -> int:
        """
        Clear all messages from queue
        
        Returns:
            Number of messages cleared
        """
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get(block=False)
                count += 1
            except queue.Empty:
                break
        logger.info(f"Cleared {count} messages from queue '{self.name}'")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics
        
        Returns:
            Dictionary with queue statistics
        """
        with self._lock:
            return {
                "name": self.name,
                "current_size": self.size(),
                "max_size": self.max_size,
                "utilization_percent": (self.size() / self.max_size * 100) if self.max_size > 0 else 0,
                "total_enqueued": self._total_enqueued,
                "total_dequeued": self._total_dequeued,
                "total_dropped": self._total_dropped,
                "is_empty": self.is_empty(),
                "is_full": self.is_full()
            }


class MessageQueueManager:
    """Manages multiple message queues"""
    
    def __init__(self):
        """Initialize queue manager"""
        self._queues: Dict[str, MessageQueue] = {}
        self._lock = threading.Lock()
        logger.info("Initialized message queue manager")
    
    def create_queue(self, name: str, max_size: int = 1000) -> MessageQueue:
        """
        Create a new message queue
        
        Args:
            name: Queue name
            max_size: Maximum queue size
            
        Returns:
            MessageQueue instance
        """
        with self._lock:
            if name in self._queues:
                logger.warning(f"Queue '{name}' already exists, returning existing queue")
                return self._queues[name]
            
            queue_obj = MessageQueue(max_size=max_size, name=name)
            self._queues[name] = queue_obj
            logger.info(f"Created queue '{name}'")
            return queue_obj
    
    def get_queue(self, name: str) -> Optional[MessageQueue]:
        """
        Get existing queue by name
        
        Args:
            name: Queue name
            
        Returns:
            MessageQueue if exists, None otherwise
        """
        return self._queues.get(name)
    
    def delete_queue(self, name: str) -> bool:
        """
        Delete a queue
        
        Args:
            name: Queue name
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if name in self._queues:
                self._queues[name].clear()
                del self._queues[name]
                logger.info(f"Deleted queue '{name}'")
                return True
            return False
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all queues
        
        Returns:
            Dictionary mapping queue names to their statistics
        """
        return {name: q.get_stats() for name, q in self._queues.items()}
    
    def clear_all(self) -> None:
        """Clear all queues"""
        for queue_obj in self._queues.values():
            queue_obj.clear()
        logger.info("Cleared all queues")
