"""
MQTT Client Service for AWS IoT Core

Manages MQTT connection, publishing, and retry logic.
"""
import logging
import json
import time
import threading
from typing import Dict, Any, Optional, Callable
from awscrt import mqtt
from awsiot import mqtt_connection_builder

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT Client for AWS IoT Core"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MQTT client
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        mqtt_config = config.get("mqtt", {})
        vehicle_config = config.get("vehicle", {})
        
        self.endpoint = mqtt_config.get("endpoint")
        self.port = mqtt_config.get("port", 8883)
        self.keep_alive = mqtt_config.get("keep_alive", 60)
        self.qos = mqtt_config.get("qos", 1)
        self.vin = vehicle_config.get("vin")
        
        # Topics
        topics = mqtt_config.get("topics", {})
        self.telemetry_topic = topics.get("telemetry", "vehicle/{vin}/telemetry").format(vin=self.vin)
        self.status_topic = topics.get("status", "vehicle/{vin}/status").format(vin=self.vin)
        
        # Certificates
        certs = mqtt_config.get("certificates", {})
        self.ca_cert = certs.get("ca_cert")
        self.client_cert = certs.get("client_cert")
        self.private_key = certs.get("private_key")
        
        self.connection: Optional[mqtt.Connection] = None
        self._connected = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Statistics
        self._publish_success = 0
        self._publish_failed = 0
        
        logger.info(f"Initialized MQTT client for VIN: {self.vin}")
    
    def connect(self) -> bool:
        """
        Connect to AWS IoT Core
        
        Returns:
            True if connected, False otherwise
        """
        try:
            # Build MQTT connection
            self.connection = mqtt_connection_builder.mtls_from_path(
                endpoint=self.endpoint,
                port=self.port,
                cert_filepath=self.client_cert,
                pri_key_filepath=self.private_key,
                ca_filepath=self.ca_cert,
                client_id=self.vin,
                clean_session=False,
                keep_alive_secs=self.keep_alive
            )
            
            # Connect
            connect_future = self.connection.connect()
            connect_future.result()
            
            self._connected = True
            logger.info(f"Connected to AWS IoT Core: {self.endpoint}")
            
            # Start heartbeat
            self._start_heartbeat()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to AWS IoT Core: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from AWS IoT Core"""
        self._running = False
        
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5.0)
        
        if self.connection and self._connected:
            disconnect_future = self.connection.disconnect()
            disconnect_future.result()
            self._connected = False
            logger.info("Disconnected from AWS IoT Core")
    
    def publish(self, topic: str, payload: Dict[str, Any], qos: Optional[int] = None) -> bool:
        """
        Publish message to topic
        
        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON encoded)
            qos: Quality of Service (0, 1, or 2)
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self._connected or not self.connection:
            logger.warning("Cannot publish: not connected")
            return False
        
        qos_level = qos if qos is not None else self.qos
        
        try:
            # Convert payload to JSON
            payload_json = json.dumps(payload)
            
            # Publish with retry
            for attempt in range(3):
                try:
                    publish_future, packet_id = self.connection.publish(
                        topic=topic,
                        payload=payload_json,
                        qos=mqtt.QoS(qos_level)
                    )
                    
                    # Wait for publish to complete
                    publish_future.result(timeout=5.0)
                    
                    self._publish_success += 1
                    logger.debug(f"Published to {topic}: packet_id={packet_id}")
                    return True
                    
                except Exception as e:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Publish attempt {attempt + 1} failed: {e}, retrying in {wait_time}s")
                    time.sleep(wait_time)
            
            # All retries failed
            self._publish_failed += 1
            logger.error(f"Failed to publish after 3 attempts")
            return False
            
        except Exception as e:
            self._publish_failed += 1
            logger.error(f"Error publishing message: {e}")
            return False
    
    def publish_telemetry(self, telemetry: Dict[str, Any]) -> bool:
        """
        Publish telemetry data
        
        Args:
            telemetry: Telemetry data dictionary
            
        Returns:
            True if published successfully
        """
        return self.publish(self.telemetry_topic, telemetry)
    
    def publish_status(self, status: Dict[str, Any]) -> bool:
        """
        Publish gateway status
        
        Args:
            status: Status data dictionary
            
        Returns:
            True if published successfully
        """
        return self.publish(self.status_topic, status)
    
    def _start_heartbeat(self) -> None:
        """Start heartbeat thread"""
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True
        )
        self._heartbeat_thread.start()
        logger.info("Started heartbeat thread")
    
    def _heartbeat_loop(self) -> None:
        """Heartbeat loop - publishes status every 30 seconds"""
        while self._running:
            try:
                status = {
                    "vin": self.vin,
                    "status": "online",
                    "timestamp": time.time(),
                    "stats": {
                        "publish_success": self._publish_success,
                        "publish_failed": self._publish_failed
                    }
                }
                
                self.publish_status(status)
                
                # Wait 30 seconds
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            "connected": self._connected,
            "endpoint": self.endpoint,
            "vin": self.vin,
            "telemetry_topic": self.telemetry_topic,
            "status_topic": self.status_topic,
            "publish_success": self._publish_success,
            "publish_failed": self._publish_failed,
            "success_rate": (
                self._publish_success / (self._publish_success + self._publish_failed) * 100
                if (self._publish_success + self._publish_failed) > 0 else 0
            )
        }
