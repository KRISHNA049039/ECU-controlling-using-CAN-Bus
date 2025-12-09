"""
Local Buffer Service with SQLite

Stores telemetry data locally during network outages and manages batching.
"""
import logging
import sqlite3
import gzip
import json
import time
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TelemetryBatch:
    """Telemetry batch"""
    batch_id: Optional[int]
    timestamp: float
    data: bytes  # Compressed JSON
    size_bytes: int
    transmitted: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "transmitted": self.transmitted
        }


class LocalBuffer:
    """Local SQLite buffer for offline telemetry storage"""
    
    # Schema version for migrations
    SCHEMA_VERSION = 1
    
    # Maximum buffer size (1 GB)
    MAX_BUFFER_SIZE = 1024 * 1024 * 1024
    
    # Maximum batch size (256 KB)
    MAX_BATCH_SIZE = 256 * 1024
    
    # Batch time window (5 seconds)
    BATCH_TIME_WINDOW = 5.0
    
    def __init__(self, db_path: str):
        """
        Initialize local buffer
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._current_batch: List[Dict[str, Any]] = []
        self._current_batch_size = 0
        self._batch_start_time = time.time()
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._initialize_database()
        
        logger.info(f"Initialized local buffer at {db_path}")
    
    def _initialize_database(self) -> None:
        """Initialize SQLite database with schema"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Create telemetry_buffer table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                batch_data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                transmitted BOOLEAN DEFAULT 0,
                created_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # Create index on transmitted for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transmitted 
            ON telemetry_buffer(transmitted, timestamp)
        """)
        
        # Create metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buffer_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Store schema version
        cursor.execute("""
            INSERT OR REPLACE INTO buffer_metadata (key, value)
            VALUES ('schema_version', ?)
        """, (str(self.SCHEMA_VERSION),))
        
        self.conn.commit()
        logger.info("Database schema initialized")
    
    def add_message(self, message: Dict[str, Any]) -> None:
        """
        Add message to current batch
        
        Args:
            message: Telemetry message dictionary
        """
        message_json = json.dumps(message)
        message_size = len(message_json.encode('utf-8'))
        
        self._current_batch.append(message)
        self._current_batch_size += message_size
        
        # Check if batch should be stored
        current_time = time.time()
        time_elapsed = current_time - self._batch_start_time
        
        if (self._current_batch_size >= self.MAX_BATCH_SIZE or 
            time_elapsed >= self.BATCH_TIME_WINDOW):
            self._store_batch()
    
    def _store_batch(self) -> None:
        """Store current batch to database"""
        if not self._current_batch:
            return
        
        # Convert batch to JSON
        batch_json = json.dumps(self._current_batch)
        batch_bytes = batch_json.encode('utf-8')
        
        # Compress with gzip
        compressed_data = gzip.compress(batch_bytes)
        
        # Store in database
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO telemetry_buffer (timestamp, batch_data, size_bytes)
            VALUES (?, ?, ?)
        """, (time.time(), compressed_data, len(compressed_data)))
        
        self.conn.commit()
        
        logger.debug(
            f"Stored batch: {len(self._current_batch)} messages, "
            f"{len(compressed_data)} bytes (compressed from {len(batch_bytes)})"
        )
        
        # Reset batch
        self._current_batch = []
        self._current_batch_size = 0
        self._batch_start_time = time.time()
        
        # Check buffer size and cleanup if needed
        self._check_buffer_size()
    
    def _check_buffer_size(self) -> None:
        """Check buffer size and remove old batches if over limit"""
        cursor = self.conn.cursor()
        
        # Get total size
        cursor.execute("SELECT SUM(size_bytes) as total FROM telemetry_buffer")
        row = cursor.fetchone()
        total_size = row['total'] if row['total'] else 0
        
        if total_size > self.MAX_BUFFER_SIZE:
            # Remove oldest transmitted batches first
            bytes_to_remove = total_size - self.MAX_BUFFER_SIZE
            
            cursor.execute("""
                DELETE FROM telemetry_buffer
                WHERE id IN (
                    SELECT id FROM telemetry_buffer
                    WHERE transmitted = 1
                    ORDER BY timestamp ASC
                    LIMIT (
                        SELECT COUNT(*) FROM telemetry_buffer
                        WHERE transmitted = 1
                        AND (SELECT SUM(size_bytes) FROM telemetry_buffer) > ?
                    )
                )
            """, (self.MAX_BUFFER_SIZE,))
            
            deleted = cursor.rowcount
            
            # If still over limit, remove oldest untransmitted
            if deleted == 0:
                cursor.execute("""
                    DELETE FROM telemetry_buffer
                    WHERE id IN (
                        SELECT id FROM telemetry_buffer
                        ORDER BY timestamp ASC
                        LIMIT 10
                    )
                """)
                deleted = cursor.rowcount
            
            self.conn.commit()
            logger.warning(f"Buffer size exceeded, removed {deleted} old batches")
    
    def get_pending_batches(self, limit: int = 100) -> List[TelemetryBatch]:
        """
        Get pending (untransmitted) batches
        
        Args:
            limit: Maximum number of batches to return
            
        Returns:
            List of TelemetryBatch objects
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, batch_data, size_bytes, transmitted
            FROM telemetry_buffer
            WHERE transmitted = 0
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,))
        
        batches = []
        for row in cursor.fetchall():
            batch = TelemetryBatch(
                batch_id=row['id'],
                timestamp=row['timestamp'],
                data=row['batch_data'],
                size_bytes=row['size_bytes'],
                transmitted=bool(row['transmitted'])
            )
            batches.append(batch)
        
        return batches
    
    def mark_transmitted(self, batch_id: int) -> None:
        """
        Mark batch as transmitted
        
        Args:
            batch_id: Batch ID to mark
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE telemetry_buffer
            SET transmitted = 1
            WHERE id = ?
        """, (batch_id,))
        self.conn.commit()
        
        logger.debug(f"Marked batch {batch_id} as transmitted")
    
    def decompress_batch(self, batch: TelemetryBatch) -> List[Dict[str, Any]]:
        """
        Decompress and parse batch data
        
        Args:
            batch: TelemetryBatch to decompress
            
        Returns:
            List of message dictionaries
        """
        try:
            # Decompress
            decompressed = gzip.decompress(batch.data)
            
            # Parse JSON
            messages = json.loads(decompressed.decode('utf-8'))
            
            return messages
        except Exception as e:
            logger.error(f"Error decompressing batch {batch.batch_id}: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get buffer statistics
        
        Returns:
            Dictionary with buffer stats
        """
        cursor = self.conn.cursor()
        
        # Total batches
        cursor.execute("SELECT COUNT(*) as count FROM telemetry_buffer")
        total_batches = cursor.fetchone()['count']
        
        # Pending batches
        cursor.execute("SELECT COUNT(*) as count FROM telemetry_buffer WHERE transmitted = 0")
        pending_batches = cursor.fetchone()['count']
        
        # Total size
        cursor.execute("SELECT SUM(size_bytes) as total FROM telemetry_buffer")
        row = cursor.fetchone()
        total_size = row['total'] if row['total'] else 0
        
        # Pending size
        cursor.execute("SELECT SUM(size_bytes) as total FROM telemetry_buffer WHERE transmitted = 0")
        row = cursor.fetchone()
        pending_size = row['total'] if row['total'] else 0
        
        return {
            "total_batches": total_batches,
            "pending_batches": pending_batches,
            "transmitted_batches": total_batches - pending_batches,
            "total_size_bytes": total_size,
            "pending_size_bytes": pending_size,
            "utilization_percent": (total_size / self.MAX_BUFFER_SIZE) * 100,
            "current_batch_messages": len(self._current_batch),
            "current_batch_size": self._current_batch_size
        }
    
    def flush(self) -> None:
        """Flush current batch to database"""
        if self._current_batch:
            self._store_batch()
    
    def close(self) -> None:
        """Close database connection"""
        if self._current_batch:
            self._store_batch()
        
        if self.conn:
            self.conn.close()
            logger.info("Closed local buffer database")
