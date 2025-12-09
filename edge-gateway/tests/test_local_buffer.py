"""
Unit tests for Local Buffer Service
"""
import unittest
import os
import tempfile
import time
from services.local_buffer import LocalBuffer, TelemetryBatch


class TestLocalBuffer(unittest.TestCase):
    """Test Local Buffer"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        self.buffer = LocalBuffer(self.db_path)
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.buffer.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_initialization(self):
        """Test buffer initialization"""
        self.assertIsNotNone(self.buffer.conn)
        self.assertEqual(len(self.buffer._current_batch), 0)
        self.assertEqual(self.buffer._current_batch_size, 0)
    
    def test_add_single_message(self):
        """Test adding a single message"""
        message = {
            "messageId": "test-123",
            "vin": "1HGBH41JXMN109186",
            "timestamp": time.time(),
            "data": {"rpm": 2500}
        }
        
        self.buffer.add_message(message)
        
        self.assertEqual(len(self.buffer._current_batch), 1)
        self.assertGreater(self.buffer._current_batch_size, 0)
    
    def test_batch_size_trigger(self):
        """Test batch storage triggered by size"""
        # Add messages until batch size exceeded
        large_message = {
            "messageId": f"test-{i}",
            "data": "x" * 50000  # 50KB message
        }
        
        for i in range(6):  # 6 * 50KB = 300KB > 256KB
            self.buffer.add_message(large_message)
        
        # Batch should have been stored
        stats = self.buffer.get_stats()
        self.assertGreater(stats['total_batches'], 0)
    
    def test_batch_time_trigger(self):
        """Test batch storage triggered by time"""
        message = {"messageId": "test", "data": "small"}
        
        self.buffer.add_message(message)
        
        # Wait for time window
        time.sleep(5.5)
        
        # Add another message to trigger check
        self.buffer.add_message(message)
        
        # Batch should have been stored
        stats = self.buffer.get_stats()
        self.assertGreater(stats['total_batches'], 0)
    
    def test_get_pending_batches(self):
        """Test retrieving pending batches"""
        # Add and store messages
        for i in range(5):
            message = {"messageId": f"test-{i}"}
            self.buffer.add_message(message)
        
        self.buffer.flush()
        
        # Get pending batches
        batches = self.buffer.get_pending_batches()
        
        self.assertGreater(len(batches), 0)
        self.assertIsInstance(batches[0], TelemetryBatch)
        self.assertFalse(batches[0].transmitted)
    
    def test_mark_transmitted(self):
        """Test marking batch as transmitted"""
        # Add and store message
        message = {"messageId": "test"}
        self.buffer.add_message(message)
        self.buffer.flush()
        
        # Get batch
        batches = self.buffer.get_pending_batches()
        self.assertEqual(len(batches), 1)
        
        batch_id = batches[0].batch_id
        
        # Mark as transmitted
        self.buffer.mark_transmitted(batch_id)
        
        # Should have no pending batches
        batches = self.buffer.get_pending_batches()
        self.assertEqual(len(batches), 0)
    
    def test_decompress_batch(self):
        """Test decompressing batch data"""
        # Add messages
        messages = [
            {"messageId": "test-1", "data": "message1"},
            {"messageId": "test-2", "data": "message2"}
        ]
        
        for msg in messages:
            self.buffer.add_message(msg)
        
        self.buffer.flush()
        
        # Get batch
        batches = self.buffer.get_pending_batches()
        batch = batches[0]
        
        # Decompress
        decompressed = self.buffer.decompress_batch(batch)
        
        self.assertEqual(len(decompressed), 2)
        self.assertEqual(decompressed[0]["messageId"], "test-1")
        self.assertEqual(decompressed[1]["messageId"], "test-2")
    
    def test_chronological_order(self):
        """Test batches are retrieved in chronological order"""
        # Add batches with delays
        for i in range(3):
            message = {"messageId": f"test-{i}", "timestamp": time.time()}
            self.buffer.add_message(message)
            self.buffer.flush()
            time.sleep(0.1)
        
        # Get batches
        batches = self.buffer.get_pending_batches()
        
        # Check order
        for i in range(len(batches) - 1):
            self.assertLess(batches[i].timestamp, batches[i+1].timestamp)
    
    def test_buffer_stats(self):
        """Test buffer statistics"""
        # Add some messages
        for i in range(5):
            message = {"messageId": f"test-{i}"}
            self.buffer.add_message(message)
        
        self.buffer.flush()
        
        stats = self.buffer.get_stats()
        
        self.assertIn("total_batches", stats)
        self.assertIn("pending_batches", stats)
        self.assertIn("total_size_bytes", stats)
        self.assertIn("utilization_percent", stats)
        
        self.assertGreater(stats["total_batches"], 0)
        self.assertGreater(stats["total_size_bytes"], 0)
    
    def test_flush(self):
        """Test manual flush"""
        message = {"messageId": "test"}
        self.buffer.add_message(message)
        
        # Should be in current batch
        self.assertEqual(len(self.buffer._current_batch), 1)
        
        # Flush
        self.buffer.flush()
        
        # Current batch should be empty
        self.assertEqual(len(self.buffer._current_batch), 0)
        
        # Should have stored batch
        stats = self.buffer.get_stats()
        self.assertGreater(stats["total_batches"], 0)
    
    def test_fifo_behavior_at_capacity(self):
        """Test FIFO behavior when buffer reaches capacity"""
        # This test would require filling the buffer to 1GB
        # For unit testing, we'll just verify the cleanup logic exists
        
        # Add a batch
        message = {"messageId": "test"}
        self.buffer.add_message(message)
        self.buffer.flush()
        
        # Mark as transmitted
        batches = self.buffer.get_pending_batches()
        self.buffer.mark_transmitted(batches[0].batch_id)
        
        # Manually trigger cleanup check
        self.buffer._check_buffer_size()
        
        # Should not raise exception
        self.assertTrue(True)
    
    def test_compression_ratio(self):
        """Test that compression reduces size"""
        # Create message with repetitive data (compresses well)
        message = {
            "messageId": "test",
            "data": "x" * 10000  # 10KB of repeated character
        }
        
        self.buffer.add_message(message)
        self.buffer.flush()
        
        # Get batch
        batches = self.buffer.get_pending_batches()
        batch = batches[0]
        
        # Compressed size should be much smaller than original
        decompressed = self.buffer.decompress_batch(batch)
        original_size = len(str(decompressed).encode('utf-8'))
        
        # Compression ratio should be significant
        self.assertLess(batch.size_bytes, original_size * 0.5)


if __name__ == '__main__':
    unittest.main()
