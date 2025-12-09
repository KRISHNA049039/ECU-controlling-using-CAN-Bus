"""
CAN Bus Interface Service

Handles CAN bus connection, frame reading, timestamping, and buffering.
"""
import time
import logging
from collections import deque
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import can

logger = logging.getLogger(__name__)


@dataclass
class CANFrame:
    """Represents a CAN frame with timestamp"""
    arbitration_id: int
    data: bytes
    timestamp: float
    is_extended_id: bool = False
    is_error_frame: bool = False
    is_remote_frame: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert frame to dictionary"""
        return {
            "arbitration_id": hex(self.arbitration_id),
            "data": self.data.hex(),
            "timestamp": self.timestamp,
            "is_extended_id": self.is_extended_id,
            "is_error_frame": self.is_error_frame,
            "is_remote_frame": self.is_remote_frame
        }


class CircularBuffer:
    """Thread-safe circular buffer for CAN frames"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self._total_received = 0
        self._total_dropped = 0
    
    def add(self, frame: CANFrame) -> None:
        """Add frame to buffer"""
        if len(self.buffer) >= self.max_size:
            self._total_dropped += 1
        self.buffer.append(frame)
        self._total_received += 1
    
    def get_all(self) -> List[CANFrame]:
        """Get all frames and clear buffer"""
        frames = list(self.buffer)
        self.buffer.clear()
        return frames
    
    def size(self) -> int:
        """Get current buffer size"""
        return len(self.buffer)
    
    def utilization(self) -> float:
        """Get buffer utilization as percentage"""
        return (len(self.buffer) / self.max_size) * 100
    
    def stats(self) -> Dict[str, int]:
        """Get buffer statistics"""
        return {
            "current_size": len(self.buffer),
            "max_size": self.max_size,
            "utilization_percent": self.utilization(),
            "total_received": self._total_received,
            "total_dropped": self._total_dropped
        }


class CANInterface:
    """CAN Bus Interface using SocketCAN"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize CAN interface
        
        Args:
            config: Configuration dictionary with keys:
                - interface: CAN interface name (e.g., 'can0')
                - bitrate: CAN bus bitrate (e.g., 500000)
                - buffer_size: Circular buffer size (default: 10000)
                - buffer_warning_threshold: Warning threshold (default: 0.8)
        """
        self.interface = config.get("interface", "can0")
        self.bitrate = config.get("bitrate", 500000)
        self.buffer_size = config.get("buffer_size", 10000)
        self.warning_threshold = config.get("buffer_warning_threshold", 0.8)
        
        self.bus: Optional[can.Bus] = None
        self.buffer = CircularBuffer(max_size=self.buffer_size)
        self.filters: List[Dict[str, int]] = []
        self._running = False
        self._last_warning_time = 0
        
        logger.info(
            f"Initialized CAN interface: {self.interface} @ {self.bitrate} bps"
        )
    
    def connect(self) -> bool:
        """
        Establish connection to CAN bus
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.bus = can.Bus(
                interface='socketcan',
                channel=self.interface,
                bitrate=self.bitrate
            )
            self._running = True
            logger.info(f"Connected to CAN bus: {self.interface}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to CAN bus: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from CAN bus"""
        self._running = False
        if self.bus:
            self.bus.shutdown()
            self.bus = None
            logger.info("Disconnected from CAN bus")
    
    def set_filters(self, filters: List[Dict[str, int]]) -> None:
        """
        Set CAN ID filters
        
        Args:
            filters: List of filter dictionaries with 'can_id' and 'can_mask'
                Example: [{"can_id": 0x7E0, "can_mask": 0x7FF}]
        """
        self.filters = filters
        if self.bus:
            self.bus.set_filters(filters)
            logger.info(f"Applied {len(filters)} CAN filters")
    
    def read_frame(self, timeout: float = 1.0) -> Optional[CANFrame]:
        """
        Read a single CAN frame with high-precision timestamp
        
        Args:
            timeout: Read timeout in seconds
            
        Returns:
            CANFrame if available, None otherwise
        """
        if not self.bus or not self._running:
            return None
        
        try:
            msg = self.bus.recv(timeout=timeout)
            if msg is None:
                return None
            
            # High-precision timestamp
            timestamp = time.time()
            
            frame = CANFrame(
                arbitration_id=msg.arbitration_id,
                data=msg.data,
                timestamp=timestamp,
                is_extended_id=msg.is_extended_id,
                is_error_frame=msg.is_error_frame,
                is_remote_frame=msg.is_remote_frame
            )
            
            # Add to buffer
            self.buffer.add(frame)
            
            # Check buffer utilization and warn if needed
            self._check_buffer_utilization()
            
            return frame
            
        except Exception as e:
            logger.error(f"Error reading CAN frame: {e}")
            return None
    
    def read_frames_batch(self, count: int = 100, timeout: float = 1.0) -> List[CANFrame]:
        """
        Read multiple CAN frames
        
        Args:
            count: Maximum number of frames to read
            timeout: Total timeout in seconds
            
        Returns:
            List of CANFrame objects
        """
        frames = []
        start_time = time.time()
        
        while len(frames) < count and (time.time() - start_time) < timeout:
            frame = self.read_frame(timeout=0.1)
            if frame:
                frames.append(frame)
        
        return frames
    
    def get_buffered_frames(self) -> List[CANFrame]:
        """
        Get all buffered frames and clear buffer
        
        Returns:
            List of buffered CANFrame objects
        """
        return self.buffer.get_all()
    
    def get_buffer_stats(self) -> Dict[str, Any]:
        """
        Get buffer statistics
        
        Returns:
            Dictionary with buffer statistics
        """
        return self.buffer.stats()
    
    def _check_buffer_utilization(self) -> None:
        """Check buffer utilization and log warning if threshold exceeded"""
        utilization = self.buffer.utilization()
        
        if utilization >= (self.warning_threshold * 100):
            # Throttle warnings to once per minute
            current_time = time.time()
            if current_time - self._last_warning_time >= 60:
                logger.warning(
                    f"CAN buffer utilization at {utilization:.1f}% "
                    f"(threshold: {self.warning_threshold * 100}%)"
                )
                self._last_warning_time = current_time
    
    def is_connected(self) -> bool:
        """Check if CAN bus is connected"""
        return self.bus is not None and self._running
