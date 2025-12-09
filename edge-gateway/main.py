#!/usr/bin/env python3
"""
ECU Diagnostics Edge Gateway - Main Application

Orchestrates all edge services for vehicle telemetry collection and transmission.
"""
import sys
import signal
import logging
import time
import threading
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from services.can_interface import CANInterface
from services.uds_decoder import UDSDecoder
from services.obd2_decoder import OBD2Decoder
from services.obd2_poller import OBD2Poller
from services.local_buffer import LocalBuffer
from services.mqtt_client import MQTTClient
from services.message_queue import MessageQueueManager, Message
from services.buffer_monitor import BufferMonitor
from services.config_loader import ConfigLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/edge-gateway.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class EdgeGateway:
    """Main Edge Gateway Application"""
    
    def __init__(self, config_path: str):
        """
        Initialize edge gateway
        
        Args:
            config_path: Path to configuration file
        """
        logger.info("Initializing ECU Diagnostics Edge Gateway")
        
        # Load configuration
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.load()
        
        # Initialize components
        self.can_interface: CANInterface = None
        self.uds_decoder = UDSDecoder()
        self.obd2_decoder = OBD2Decoder()
        self.obd2_poller: OBD2Poller = None
        self.local_buffer: LocalBuffer = None
        self.mqtt_client: MQTTClient = None
        self.buffer_monitor: BufferMonitor = None
        
        # Message queues
        self.queue_manager = MessageQueueManager()
        self.can_queue = self.queue_manager.create_queue("can_frames", max_size=1000)
        self.decoded_queue = self.queue_manager.create_queue("decoded_messages", max_size=500)
        
        # Worker threads
        self.workers = []
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def initialize(self) -> bool:
        """
        Initialize all services
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Initialize CAN interface
            logger.info("Initializing CAN interface")
            self.can_interface = CANInterface(self.config.get("can", {}))
            
            # Initialize buffer monitor
            logger.info("Initializing buffer monitor")
            self.buffer_monitor = BufferMonitor(
                self.can_interface,
                warning_threshold=self.config.get("can", {}).get("buffer_warning_threshold", 0.8)
            )
            
            # Initialize local buffer
            logger.info("Initializing local buffer")
            buffer_config = self.config.get("buffer", {})
            db_path = buffer_config.get("db_path", "data/telemetry_buffer.db")
            self.local_buffer = LocalBuffer(db_path)
            
            # Initialize MQTT client
            logger.info("Initializing MQTT client")
            self.mqtt_client = MQTTClient(self.config)
            
            # Initialize OBD-II poller
            if self.config.get("obd2", {}).get("enabled", True):
                logger.info("Initializing OBD-II poller")
                self.obd2_poller = OBD2Poller(self.config)
                self.obd2_poller.set_callback(self._request_obd2_pid)
            
            logger.info("All services initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            return False
    
    def start(self) -> bool:
        """
        Start all services
        
        Returns:
            True if started successfully
        """
        try:
            logger.info("Starting ECU Diagnostics Edge Gateway")
            
            # Connect to CAN bus
            if not self.can_interface.connect():
                logger.error("Failed to connect to CAN bus")
                return False
            
            # Start buffer monitor
            self.buffer_monitor.start(interval=5.0)
            
            # Connect to MQTT
            if not self.mqtt_client.connect():
                logger.warning("Failed to connect to MQTT, will retry")
            
            # Start OBD-II poller
            if self.obd2_poller:
                self.obd2_poller.start()
            
            # Start worker threads
            self.running = True
            self._start_workers()
            
            logger.info("Edge Gateway started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start services: {e}")
            return False
    
    def _start_workers(self) -> None:
        """Start worker threads"""
        # CAN reader thread
        can_reader = threading.Thread(target=self._can_reader_worker, daemon=True)
        can_reader.start()
        self.workers.append(can_reader)
        
        # Decoder thread
        decoder = threading.Thread(target=self._decoder_worker, daemon=True)
        decoder.start()
        self.workers.append(decoder)
        
        # Buffer/MQTT thread
        publisher = threading.Thread(target=self._publisher_worker, daemon=True)
        publisher.start()
        self.workers.append(publisher)
        
        logger.info(f"Started {len(self.workers)} worker threads")
    
    def _can_reader_worker(self) -> None:
        """Worker thread to read CAN frames"""
        logger.info("CAN reader worker started")
        
        while self.running:
            try:
                frame = self.can_interface.read_frame(timeout=0.1)
                if frame:
                    # Create message
                    msg = Message(
                        message_type="can_frame",
                        payload=frame.to_dict(),
                        timestamp=frame.timestamp,
                        source="can_interface"
                    )
                    self.can_queue.enqueue(msg, block=False)
                    
            except Exception as e:
                logger.error(f"Error in CAN reader: {e}")
                time.sleep(1)
        
        logger.info("CAN reader worker stopped")
    
    def _decoder_worker(self) -> None:
        """Worker thread to decode messages"""
        logger.info("Decoder worker started")
        
        while self.running:
            try:
                # Get CAN frame from queue
                msg = self.can_queue.dequeue(timeout=0.1)
                if not msg:
                    continue
                
                # Try UDS decoding
                can_data = bytes.fromhex(msg.payload.get("data", ""))
                can_id = int(msg.payload.get("arbitration_id", "0x0"), 16)
                
                # Check if it's a UDS message (ECU response)
                if can_id >= 0x7E8 and can_id <= 0x7EF:
                    uds_msg = self.uds_decoder.decode_message(can_data, can_id)
                    if uds_msg:
                        decoded_msg = Message(
                            message_type="uds",
                            payload=uds_msg.to_dict(),
                            timestamp=msg.timestamp,
                            source="uds_decoder"
                        )
                        self.decoded_queue.enqueue(decoded_msg, block=False)
                
                # Check if it's an OBD-II message
                if can_id >= 0x7E8 and can_id <= 0x7EF:
                    obd2_msg = self.obd2_decoder.decode_message(can_data)
                    if obd2_msg and obd2_msg.parameters:
                        decoded_msg = Message(
                            message_type="obd2",
                            payload=obd2_msg.to_dict(),
                            timestamp=msg.timestamp,
                            source="obd2_decoder"
                        )
                        self.decoded_queue.enqueue(decoded_msg, block=False)
                        
            except Exception as e:
                logger.error(f"Error in decoder: {e}")
        
        logger.info("Decoder worker stopped")
    
    def _publisher_worker(self) -> None:
        """Worker thread to publish telemetry"""
        logger.info("Publisher worker started")
        
        while self.running:
            try:
                # Get decoded message
                msg = self.decoded_queue.dequeue(timeout=0.1)
                if not msg:
                    continue
                
                # Create telemetry message
                telemetry = {
                    "messageId": f"{int(time.time() * 1000)}",
                    "vin": self.config.get("vehicle", {}).get("vin"),
                    "timestamp": msg.timestamp,
                    "gatewayId": self.config.get("vehicle", {}).get("gateway_id"),
                    "telemetryType": msg.message_type,
                    "data": msg.payload
                }
                
                # Add to local buffer
                self.local_buffer.add_message(telemetry)
                
                # Try to publish if connected
                if self.mqtt_client.is_connected():
                    # Get pending batches
                    batches = self.local_buffer.get_pending_batches(limit=10)
                    
                    for batch in batches:
                        # Decompress batch
                        messages = self.local_buffer.decompress_batch(batch)
                        
                        # Publish each message
                        for message in messages:
                            if self.mqtt_client.publish_telemetry(message):
                                # Mark batch as transmitted
                                self.local_buffer.mark_transmitted(batch.batch_id)
                            else:
                                # Failed to publish, will retry later
                                break
                
            except Exception as e:
                logger.error(f"Error in publisher: {e}")
        
        logger.info("Publisher worker stopped")
    
    def _request_obd2_pid(self, pid: int) -> None:
        """
        Request OBD-II PID from ECU
        
        Args:
            pid: PID to request
        """
        # In a real implementation, this would send a CAN message
        # For now, we just log it
        logger.debug(f"Requesting OBD-II PID: {hex(pid)}")
    
    def stop(self) -> None:
        """Stop all services"""
        logger.info("Stopping ECU Diagnostics Edge Gateway")
        
        self.running = False
        
        # Stop OBD-II poller
        if self.obd2_poller:
            self.obd2_poller.stop()
        
        # Stop buffer monitor
        if self.buffer_monitor:
            self.buffer_monitor.stop()
        
        # Disconnect MQTT
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        
        # Flush local buffer
        if self.local_buffer:
            self.local_buffer.flush()
            self.local_buffer.close()
        
        # Disconnect CAN
        if self.can_interface:
            self.can_interface.disconnect()
        
        # Wait for workers
        for worker in self.workers:
            worker.join(timeout=2.0)
        
        logger.info("Edge Gateway stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully")
        self.stop()
        sys.exit(0)
    
    def run(self) -> None:
        """Run the edge gateway"""
        if not self.initialize():
            logger.error("Failed to initialize, exiting")
            sys.exit(1)
        
        if not self.start():
            logger.error("Failed to start, exiting")
            sys.exit(1)
        
        # Keep running
        try:
            while self.running:
                time.sleep(1)
                
                # Print stats every 60 seconds
                if int(time.time()) % 60 == 0:
                    self._print_stats()
                    
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()
    
    def _print_stats(self) -> None:
        """Print system statistics"""
        logger.info("=== System Statistics ===")
        
        # CAN stats
        can_stats = self.can_interface.get_buffer_stats()
        logger.info(f"CAN Buffer: {can_stats['current_size']}/{can_stats['max_size']} "
                   f"({can_stats['utilization_percent']:.1f}%)")
        
        # Queue stats
        queue_stats = self.queue_manager.get_all_stats()
        for name, stats in queue_stats.items():
            logger.info(f"Queue '{name}': {stats['current_size']}/{stats['max_size']}")
        
        # Buffer stats
        buffer_stats = self.local_buffer.get_stats()
        logger.info(f"Local Buffer: {buffer_stats['pending_batches']} pending batches, "
                   f"{buffer_stats['utilization_percent']:.1f}% full")
        
        # MQTT stats
        mqtt_stats = self.mqtt_client.get_stats()
        logger.info(f"MQTT: Connected={mqtt_stats['connected']}, "
                   f"Success={mqtt_stats['publish_success']}, "
                   f"Failed={mqtt_stats['publish_failed']}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ECU Diagnostics Edge Gateway')
    parser.add_argument('--config', default='config/dev.yaml',
                       help='Path to configuration file')
    args = parser.parse_args()
    
    # Create logs directory
    Path('logs').mkdir(exist_ok=True)
    
    # Create and run gateway
    gateway = EdgeGateway(args.config)
    gateway.run()


if __name__ == '__main__':
    main()
