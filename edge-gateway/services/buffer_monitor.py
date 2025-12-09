"""
Buffer Monitoring Service

Monitors CAN buffer utilization and collects metrics.
"""
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class BufferMetrics:
    """Buffer metrics snapshot"""
    timestamp: float
    current_size: int
    max_size: int
    utilization_percent: float
    total_received: int
    total_dropped: int
    frames_per_second: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            "timestamp": self.timestamp,
            "current_size": self.current_size,
            "max_size": self.max_size,
            "utilization_percent": round(self.utilization_percent, 2),
            "total_received": self.total_received,
            "total_dropped": self.total_dropped,
            "frames_per_second": round(self.frames_per_second, 2)
        }


class BufferMonitor:
    """Monitors buffer utilization and collects metrics"""
    
    def __init__(self, can_interface, warning_threshold: float = 0.8):
        """
        Initialize buffer monitor
        
        Args:
            can_interface: CANInterface instance to monitor
            warning_threshold: Utilization threshold for warnings (0.0-1.0)
        """
        self.can_interface = can_interface
        self.warning_threshold = warning_threshold
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._metrics_history = []
        self._max_history_size = 1000
        self._last_received_count = 0
        self._last_check_time = time.time()
        
        logger.info(f"Initialized buffer monitor with {warning_threshold*100}% warning threshold")
    
    def start(self, interval: float = 5.0) -> None:
        """
        Start monitoring buffer
        
        Args:
            interval: Monitoring interval in seconds
        """
        if self._running:
            logger.warning("Buffer monitor already running")
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self._monitor_thread.start()
        logger.info(f"Started buffer monitoring (interval: {interval}s)")
    
    def stop(self) -> None:
        """Stop monitoring buffer"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("Stopped buffer monitoring")
    
    def _monitor_loop(self, interval: float) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                self._collect_metrics()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error in buffer monitoring loop: {e}")
    
    def _collect_metrics(self) -> None:
        """Collect current buffer metrics"""
        stats = self.can_interface.get_buffer_stats()
        current_time = time.time()
        
        # Calculate frames per second
        time_delta = current_time - self._last_check_time
        received_delta = stats["total_received"] - self._last_received_count
        frames_per_second = received_delta / time_delta if time_delta > 0 else 0.0
        
        metrics = BufferMetrics(
            timestamp=current_time,
            current_size=stats["current_size"],
            max_size=stats["max_size"],
            utilization_percent=stats["utilization_percent"],
            total_received=stats["total_received"],
            total_dropped=stats["total_dropped"],
            frames_per_second=frames_per_second
        )
        
        # Store metrics
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self._max_history_size:
            self._metrics_history.pop(0)
        
        # Log metrics
        self._log_metrics(metrics)
        
        # Check for warnings
        self._check_warnings(metrics)
        
        # Update tracking variables
        self._last_received_count = stats["total_received"]
        self._last_check_time = current_time
    
    def _log_metrics(self, metrics: BufferMetrics) -> None:
        """Log buffer metrics"""
        logger.debug(
            f"Buffer metrics: "
            f"size={metrics.current_size}/{metrics.max_size} "
            f"({metrics.utilization_percent:.1f}%), "
            f"received={metrics.total_received}, "
            f"dropped={metrics.total_dropped}, "
            f"fps={metrics.frames_per_second:.1f}"
        )
    
    def _check_warnings(self, metrics: BufferMetrics) -> None:
        """Check metrics and log warnings if thresholds exceeded"""
        # Check utilization threshold
        if metrics.utilization_percent >= (self.warning_threshold * 100):
            logger.warning(
                f"Buffer utilization at {metrics.utilization_percent:.1f}% "
                f"(threshold: {self.warning_threshold * 100}%)"
            )
        
        # Check for dropped frames
        if metrics.total_dropped > 0:
            logger.warning(
                f"Buffer has dropped {metrics.total_dropped} frames "
                f"({(metrics.total_dropped / metrics.total_received * 100):.2f}% of total)"
            )
        
        # Check for high frame rate
        if metrics.frames_per_second > 1000:
            logger.warning(
                f"High CAN frame rate detected: {metrics.frames_per_second:.1f} fps"
            )
    
    def get_current_metrics(self) -> Optional[BufferMetrics]:
        """
        Get most recent metrics
        
        Returns:
            Latest BufferMetrics or None if no metrics collected
        """
        if not self._metrics_history:
            return None
        return self._metrics_history[-1]
    
    def get_metrics_history(self, count: int = 100) -> list[BufferMetrics]:
        """
        Get historical metrics
        
        Args:
            count: Number of recent metrics to return
            
        Returns:
            List of BufferMetrics
        """
        return self._metrics_history[-count:]
    
    def get_average_utilization(self, window_seconds: float = 60.0) -> float:
        """
        Calculate average buffer utilization over time window
        
        Args:
            window_seconds: Time window in seconds
            
        Returns:
            Average utilization percentage
        """
        if not self._metrics_history:
            return 0.0
        
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        recent_metrics = [
            m for m in self._metrics_history
            if m.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            return 0.0
        
        avg_utilization = sum(m.utilization_percent for m in recent_metrics) / len(recent_metrics)
        return avg_utilization
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get monitoring summary
        
        Returns:
            Dictionary with monitoring summary
        """
        current = self.get_current_metrics()
        if not current:
            return {"status": "no_data"}
        
        return {
            "status": "active" if self._running else "stopped",
            "current_metrics": current.to_dict(),
            "average_utilization_1min": round(self.get_average_utilization(60), 2),
            "average_utilization_5min": round(self.get_average_utilization(300), 2),
            "metrics_collected": len(self._metrics_history),
            "warning_threshold": self.warning_threshold * 100
        }
