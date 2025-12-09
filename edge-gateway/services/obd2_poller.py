"""
OBD-II PID Polling Service

Polls ECU for OBD-II parameters at configurable intervals.
"""
import logging
import time
import threading
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PIDConfig:
    """PID polling configuration"""
    pid: int
    name: str
    interval_ms: int
    enabled: bool = True
    last_poll_time: float = 0.0
    
    def should_poll(self, current_time: float) -> bool:
        """Check if PID should be polled now"""
        if not self.enabled:
            return False
        
        interval_seconds = self.interval_ms / 1000.0
        return (current_time - self.last_poll_time) >= interval_seconds


class OBD2Poller:
    """OBD-II PID Polling Scheduler"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OBD-II poller
        
        Args:
            config: Configuration dictionary with PID list and intervals
        """
        self.config = config
        self.pid_configs: List[PIDConfig] = []
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None
        
        # Load PID configurations
        self._load_pid_configs()
        
        logger.info(f"Initialized OBD-II poller with {len(self.pid_configs)} PIDs")
    
    def _load_pid_configs(self) -> None:
        """Load PID configurations from config"""
        pids = self.config.get("obd2", {}).get("pids", [])
        
        for pid_config in pids:
            pid_value = int(pid_config.get("pid", "0x00"), 16)
            name = pid_config.get("name", f"pid_{hex(pid_value)}")
            interval_ms = pid_config.get("interval_ms", 1000)
            enabled = pid_config.get("enabled", True)
            
            pid_cfg = PIDConfig(
                pid=pid_value,
                name=name,
                interval_ms=interval_ms,
                enabled=enabled
            )
            
            self.pid_configs.append(pid_cfg)
            logger.debug(f"Loaded PID config: {name} ({hex(pid_value)}) @ {interval_ms}ms")
    
    def set_callback(self, callback: Callable[[int], None]) -> None:
        """
        Set callback function for PID requests
        
        Args:
            callback: Function to call with PID value when polling
        """
        self._callback = callback
    
    def start(self) -> None:
        """Start polling scheduler"""
        if self._running:
            logger.warning("OBD-II poller already running")
            return
        
        if not self._callback:
            logger.error("Cannot start poller: no callback set")
            return
        
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True
        )
        self._poll_thread.start()
        logger.info("Started OBD-II polling scheduler")
    
    def stop(self) -> None:
        """Stop polling scheduler"""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5.0)
        logger.info("Stopped OBD-II polling scheduler")
    
    def _poll_loop(self) -> None:
        """Main polling loop"""
        while self._running:
            try:
                current_time = time.time()
                
                # Check each PID
                for pid_config in self.pid_configs:
                    if pid_config.should_poll(current_time):
                        # Request PID
                        if self._callback:
                            self._callback(pid_config.pid)
                        
                        # Update last poll time
                        pid_config.last_poll_time = current_time
                        
                        logger.debug(f"Polled PID {hex(pid_config.pid)} ({pid_config.name})")
                
                # Sleep for minimum interval (10ms)
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
    
    def enable_pid(self, pid: int) -> bool:
        """
        Enable polling for specific PID
        
        Args:
            pid: PID to enable
            
        Returns:
            True if found and enabled, False otherwise
        """
        for pid_config in self.pid_configs:
            if pid_config.pid == pid:
                pid_config.enabled = True
                logger.info(f"Enabled PID {hex(pid)}")
                return True
        return False
    
    def disable_pid(self, pid: int) -> bool:
        """
        Disable polling for specific PID
        
        Args:
            pid: PID to disable
            
        Returns:
            True if found and disabled, False otherwise
        """
        for pid_config in self.pid_configs:
            if pid_config.pid == pid:
                pid_config.enabled = False
                logger.info(f"Disabled PID {hex(pid)}")
                return True
        return False
    
    def set_interval(self, pid: int, interval_ms: int) -> bool:
        """
        Set polling interval for specific PID
        
        Args:
            pid: PID to configure
            interval_ms: Polling interval in milliseconds (100-5000)
            
        Returns:
            True if found and updated, False otherwise
        """
        if interval_ms < 100 or interval_ms > 5000:
            logger.error(f"Invalid interval: {interval_ms}ms (must be 100-5000)")
            return False
        
        for pid_config in self.pid_configs:
            if pid_config.pid == pid:
                pid_config.interval_ms = interval_ms
                logger.info(f"Set PID {hex(pid)} interval to {interval_ms}ms")
                return True
        return False
    
    def add_pid(self, pid: int, name: str, interval_ms: int = 1000) -> None:
        """
        Add new PID to polling list
        
        Args:
            pid: PID value
            name: PID name
            interval_ms: Polling interval in milliseconds
        """
        # Check if already exists
        for pid_config in self.pid_configs:
            if pid_config.pid == pid:
                logger.warning(f"PID {hex(pid)} already exists")
                return
        
        pid_config = PIDConfig(
            pid=pid,
            name=name,
            interval_ms=interval_ms,
            enabled=True
        )
        
        self.pid_configs.append(pid_config)
        logger.info(f"Added PID {hex(pid)} ({name}) @ {interval_ms}ms")
    
    def remove_pid(self, pid: int) -> bool:
        """
        Remove PID from polling list
        
        Args:
            pid: PID to remove
            
        Returns:
            True if found and removed, False otherwise
        """
        for i, pid_config in enumerate(self.pid_configs):
            if pid_config.pid == pid:
                self.pid_configs.pop(i)
                logger.info(f"Removed PID {hex(pid)}")
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get polling statistics
        
        Returns:
            Dictionary with polling stats
        """
        enabled_count = sum(1 for p in self.pid_configs if p.enabled)
        
        return {
            "running": self._running,
            "total_pids": len(self.pid_configs),
            "enabled_pids": enabled_count,
            "disabled_pids": len(self.pid_configs) - enabled_count,
            "pids": [
                {
                    "pid": hex(p.pid),
                    "name": p.name,
                    "interval_ms": p.interval_ms,
                    "enabled": p.enabled,
                    "last_poll": p.last_poll_time
                }
                for p in self.pid_configs
            ]
        }
