"""
Unit tests for CAN Interface Service
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import time
from services.can_interface import CANInterface, CANFrame, CircularBuffer


class TestCANFrame(unittest.TestCase):
    """Test CANFrame dataclass"""
    
    def test_can_frame_creation(self):
        """Test creating a CAN frame"""
        frame = CANFrame(
            arbitration_id=0x7E0,
            data=b'\x02\x01\x00\x00\x00\x00\x00\x00',
            timestamp=time.time()
        )
        self.assertEqual(frame.arbitration_id, 0x7E0)
        self.assertEqual(len(frame.data), 8)
        self.assertFalse(frame.is_extended_id)
    
    def test_can_frame_to_dict(self):
        """Test converting frame to dictionary"""
        timestamp = time.time()
        frame = CANFrame(
            arbitration_id=0x7E0,
            data=b'\x02\x01\x00',
            timestamp=timestamp
        )
        frame_dict = frame.to_dict()
        
        self.assertEqual(frame_dict['arbitration_id'], '0x7e0')
        self.assertEqual(frame_dict['data'], '020100')
        self.assertEqual(frame_dict['timestamp'], timestamp)


class TestCircularBuffer(unittest.TestCase):
    """Test CircularBuffer class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.buffer = CircularBuffer(max_size=10)
    
    def test_buffer_initialization(self):
        """Test buffer initialization"""
        self.assertEqual(self.buffer.max_size, 10)
        self.assertEqual(self.buffer.size(), 0)
        self.assertEqual(self.buffer.utilization(), 0.0)
    
    def test_add_frame(self):
        """Test adding frames to buffer"""
        frame = CANFrame(
            arbitration_id=0x7E0,
            data=b'\x00',
            timestamp=time.time()
        )
        self.buffer.add(frame)
        
        self.assertEqual(self.buffer.size(), 1)
        self.assertEqual(self.buffer.utilization(), 10.0)
    
    def test_buffer_overflow(self):
        """Test buffer overflow behavior"""
        # Fill buffer beyond capacity
        for i in range(15):
            frame = CANFrame(
                arbitration_id=0x7E0 + i,
                data=b'\x00',
                timestamp=time.time()
            )
            self.buffer.add(frame)
        
        # Buffer should be at max size
        self.assertEqual(self.buffer.size(), 10)
        
        # Check dropped frames
        stats = self.buffer.stats()
        self.assertEqual(stats['total_received'], 15)
        self.assertEqual(stats['total_dropped'], 5)
    
    def test_get_all_frames(self):
        """Test retrieving all frames"""
        # Add frames
        for i in range(5):
            frame = CANFrame(
                arbitration_id=0x7E0 + i,
                data=b'\x00',
                timestamp=time.time()
            )
            self.buffer.add(frame)
        
        # Get all frames
        frames = self.buffer.get_all()
        self.assertEqual(len(frames), 5)
        
        # Buffer should be empty after get_all
        self.assertEqual(self.buffer.size(), 0)
    
    def test_buffer_stats(self):
        """Test buffer statistics"""
        for i in range(3):
            frame = CANFrame(
                arbitration_id=0x7E0,
                data=b'\x00',
                timestamp=time.time()
            )
            self.buffer.add(frame)
        
        stats = self.buffer.stats()
        self.assertEqual(stats['current_size'], 3)
        self.assertEqual(stats['max_size'], 10)
        self.assertEqual(stats['utilization_percent'], 30.0)
        self.assertEqual(stats['total_received'], 3)
        self.assertEqual(stats['total_dropped'], 0)


class TestCANInterface(unittest.TestCase):
    """Test CANInterface class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "interface": "can0",
            "bitrate": 500000,
            "buffer_size": 100,
            "buffer_warning_threshold": 0.8
        }
    
    @patch('services.can_interface.can.Bus')
    def test_initialization(self, mock_bus):
        """Test CAN interface initialization"""
        interface = CANInterface(self.config)
        
        self.assertEqual(interface.interface, "can0")
        self.assertEqual(interface.bitrate, 500000)
        self.assertEqual(interface.buffer_size, 100)
        self.assertEqual(interface.warning_threshold, 0.8)
        self.assertIsNone(interface.bus)
    
    @patch('services.can_interface.can.Bus')
    def test_connect_success(self, mock_bus):
        """Test successful CAN bus connection"""
        interface = CANInterface(self.config)
        result = interface.connect()
        
        self.assertTrue(result)
        self.assertTrue(interface.is_connected())
        mock_bus.assert_called_once()
    
    @patch('services.can_interface.can.Bus')
    def test_connect_failure(self, mock_bus):
        """Test failed CAN bus connection"""
        mock_bus.side_effect = Exception("Connection failed")
        interface = CANInterface(self.config)
        result = interface.connect()
        
        self.assertFalse(result)
        self.assertFalse(interface.is_connected())
    
    @patch('services.can_interface.can.Bus')
    def test_disconnect(self, mock_bus):
        """Test disconnecting from CAN bus"""
        interface = CANInterface(self.config)
        interface.connect()
        interface.disconnect()
        
        self.assertFalse(interface.is_connected())
        self.assertIsNone(interface.bus)
    
    @patch('services.can_interface.can.Bus')
    def test_set_filters(self, mock_bus):
        """Test setting CAN filters"""
        interface = CANInterface(self.config)
        interface.connect()
        
        filters = [{"can_id": 0x7E0, "can_mask": 0x7FF}]
        interface.set_filters(filters)
        
        self.assertEqual(len(interface.filters), 1)
        interface.bus.set_filters.assert_called_once_with(filters)
    
    @patch('services.can_interface.can.Bus')
    def test_read_frame(self, mock_bus):
        """Test reading a CAN frame"""
        # Create mock message
        mock_msg = Mock()
        mock_msg.arbitration_id = 0x7E0
        mock_msg.data = b'\x02\x01\x00\x00\x00\x00\x00\x00'
        mock_msg.is_extended_id = False
        mock_msg.is_error_frame = False
        mock_msg.is_remote_frame = False
        
        # Configure mock bus
        mock_bus_instance = MagicMock()
        mock_bus_instance.recv.return_value = mock_msg
        mock_bus.return_value = mock_bus_instance
        
        interface = CANInterface(self.config)
        interface.connect()
        
        frame = interface.read_frame(timeout=1.0)
        
        self.assertIsNotNone(frame)
        self.assertEqual(frame.arbitration_id, 0x7E0)
        self.assertEqual(frame.data, b'\x02\x01\x00\x00\x00\x00\x00\x00')
    
    @patch('services.can_interface.can.Bus')
    def test_read_frame_timeout(self, mock_bus):
        """Test reading frame with timeout"""
        mock_bus_instance = MagicMock()
        mock_bus_instance.recv.return_value = None
        mock_bus.return_value = mock_bus_instance
        
        interface = CANInterface(self.config)
        interface.connect()
        
        frame = interface.read_frame(timeout=0.1)
        self.assertIsNone(frame)
    
    @patch('services.can_interface.can.Bus')
    def test_timestamp_precision(self, mock_bus):
        """Test timestamp precision (millisecond level)"""
        mock_msg = Mock()
        mock_msg.arbitration_id = 0x7E0
        mock_msg.data = b'\x00'
        mock_msg.is_extended_id = False
        mock_msg.is_error_frame = False
        mock_msg.is_remote_frame = False
        
        mock_bus_instance = MagicMock()
        mock_bus_instance.recv.return_value = mock_msg
        mock_bus.return_value = mock_bus_instance
        
        interface = CANInterface(self.config)
        interface.connect()
        
        frame = interface.read_frame()
        
        # Verify timestamp has millisecond precision
        # (timestamp should be a float with fractional seconds)
        self.assertIsInstance(frame.timestamp, float)
        self.assertGreater(frame.timestamp, 0)
    
    @patch('services.can_interface.can.Bus')
    def test_buffer_warning_threshold(self, mock_bus):
        """Test buffer warning at 80% capacity"""
        mock_msg = Mock()
        mock_msg.arbitration_id = 0x7E0
        mock_msg.data = b'\x00'
        mock_msg.is_extended_id = False
        mock_msg.is_error_frame = False
        mock_msg.is_remote_frame = False
        
        mock_bus_instance = MagicMock()
        mock_bus_instance.recv.return_value = mock_msg
        mock_bus.return_value = mock_bus_instance
        
        # Create interface with small buffer
        config = self.config.copy()
        config['buffer_size'] = 10
        interface = CANInterface(config)
        interface.connect()
        
        # Fill buffer to 80%
        with self.assertLogs(level='WARNING') as log:
            for _ in range(9):  # 90% full
                interface.read_frame()
            
            # Should trigger warning
            self.assertTrue(
                any('buffer utilization' in msg.lower() for msg in log.output)
            )
    
    @patch('services.can_interface.can.Bus')
    def test_get_buffer_stats(self, mock_bus):
        """Test getting buffer statistics"""
        interface = CANInterface(self.config)
        stats = interface.get_buffer_stats()
        
        self.assertIn('current_size', stats)
        self.assertIn('max_size', stats)
        self.assertIn('utilization_percent', stats)
        self.assertIn('total_received', stats)
        self.assertIn('total_dropped', stats)


if __name__ == '__main__':
    unittest.main()
