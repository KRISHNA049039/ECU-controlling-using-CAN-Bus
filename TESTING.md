# ECU Diagnostics System - Testing Guide

This document provides comprehensive instructions for testing the ECU Diagnostics System components.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Running Unit Tests](#running-unit-tests)
4. [Testing Edge Gateway Services](#testing-edge-gateway-services)
5. [Testing with Simulated CAN Data](#testing-with-simulated-can-data)
6. [Integration Testing](#integration-testing)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- Python 3.11 or higher
- pip (Python package manager)
- Virtual CAN interface (for CAN bus testing)
- Git

### Optional Tools

- CAN utilities (`can-utils` package on Linux)
- Wireshark with CAN plugin (for protocol analysis)
- pytest-cov (for coverage reports)

---

## Environment Setup

### 1. Create Python Virtual Environment

```bash
cd edge-gateway
python -m venv venv
```

### 2. Activate Virtual Environment

**On Windows:**
```cmd
venv\Scripts\activate
```

**On Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Testing Dependencies

```bash
pip install pytest pytest-cov pytest-mock
```

### 5. Set Up Virtual CAN Interface (Linux Only)

```bash
# Load vcan kernel module
sudo modprobe vcan

# Create virtual CAN interface
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# Verify interface is up
ip link show vcan0
```

**On Windows:** Use a CAN simulator or hardware adapter.

---

## Running Unit Tests

### Run All Tests

```bash
cd edge-gateway
python -m pytest tests/
```

### Run Specific Test File

```bash
# Test CAN interface
python -m pytest tests/test_can_interface.py

# Test UDS decoder
python -m pytest tests/test_uds_decoder.py
```

### Run Specific Test Class or Method

```bash
# Run specific test class
python -m pytest tests/test_can_interface.py::TestCANInterface

# Run specific test method
python -m pytest tests/test_can_interface.py::TestCANInterface::test_connect_success
```

### Run Tests with Verbose Output

```bash
python -m pytest tests/ -v
```

### Run Tests with Coverage Report

```bash
# Generate coverage report
python -m pytest tests/ --cov=services --cov-report=html

# View coverage report
# Open htmlcov/index.html in your browser
```

### Run Tests with Detailed Output

```bash
python -m pytest tests/ -vv --tb=short
```

---

## Testing Edge Gateway Services

### Test 1: CAN Interface Service

#### Manual Test with Virtual CAN

**Terminal 1 - Start CAN Interface:**
```python
# test_can_manual.py
from services.can_interface import CANInterface
import time

config = {
    "interface": "vcan0",
    "bitrate": 500000,
    "buffer_size": 100,
    "buffer_warning_threshold": 0.8
}

can_interface = CANInterface(config)
if can_interface.connect():
    print("Connected to CAN bus")
    
    # Read frames for 10 seconds
    for i in range(100):
        frame = can_interface.read_frame(timeout=0.1)
        if frame:
            print(f"Received frame: ID={hex(frame.arbitration_id)}, Data={frame.data.hex()}")
    
    # Print buffer stats
    stats = can_interface.get_buffer_stats()
    print(f"Buffer stats: {stats}")
    
    can_interface.disconnect()
else:
    print("Failed to connect to CAN bus")
```

**Terminal 2 - Send Test CAN Messages:**
```bash
# Send single frame
cansend vcan0 7E0#0201000000000000

# Send multiple frames
for i in {1..10}; do
    cansend vcan0 7E0#0201000000000000
    sleep 0.1
done

# Monitor CAN traffic
candump vcan0
```

#### Expected Results
- CAN interface connects successfully
- Frames are received and timestamped
- Buffer statistics show correct counts
- No errors in logs

---

### Test 2: UDS Decoder Service

#### Unit Test Execution

```bash
python -m pytest tests/test_uds_decoder.py -v
```

#### Manual Test with Sample Data

```python
# test_uds_manual.py
from services.uds_decoder import UDSDecoder
from services.uds_validator import UDSValidator

decoder = UDSDecoder()
validator = UDSValidator()

# Test 1: Tester Present
print("Test 1: Tester Present")
data = bytes([0x3E, 0x00])
message = decoder.decode_message(data, 0x7E0)
print(f"Service: {message.service_name}")
print(f"Is Response: {message.is_response}")

# Test 2: Read DTC Information
print("\nTest 2: Read DTC Information")
data = bytes([
    0x59, 0x02, 0xFF,
    0x01, 0x03, 0x01, 0x08,  # P0301
    0x01, 0x04, 0x20, 0x48   # P0420
])
message = decoder.decode_message(data, 0x7E0)
print(f"DTCs found: {len(message.dtc_info)}")
for dtc in message.dtc_info:
    print(f"  - {dtc.code}: {dtc.severity} (status: {hex(dtc.status_byte)})")

# Test 3: Validate Message
print("\nTest 3: Message Validation")
valid_data = bytes([0x22, 0xF1, 0x90])
result = validator.validate_message(valid_data, 0x7E0)
print(f"Valid: {result.is_valid}")

invalid_data = bytes([0xFF, 0x00])
result = validator.validate_message(invalid_data, 0x7E0)
print(f"Invalid: {result.is_valid}, Error: {result.error_message}")
```

**Run the test:**
```bash
python test_uds_manual.py
```

#### Expected Results
- Tester Present decoded correctly
- DTCs extracted with proper codes (P0301, P0420)
- Severity levels assigned correctly
- Validation catches invalid messages

---

### Test 3: Buffer Monitor Service

#### Manual Test

```python
# test_buffer_monitor.py
from services.can_interface import CANInterface
from services.buffer_monitor import BufferMonitor
import time

config = {
    "interface": "vcan0",
    "bitrate": 500000,
    "buffer_size": 100,
    "buffer_warning_threshold": 0.8
}

can_interface = CANInterface(config)
can_interface.connect()

# Start buffer monitoring
monitor = BufferMonitor(can_interface, warning_threshold=0.8)
monitor.start(interval=2.0)

print("Monitoring buffer for 30 seconds...")
time.sleep(30)

# Get monitoring summary
summary = monitor.get_summary()
print(f"\nMonitoring Summary:")
print(f"  Status: {summary['status']}")
print(f"  Current Utilization: {summary['current_metrics']['utilization_percent']}%")
print(f"  Avg Utilization (1min): {summary['average_utilization_1min']}%")
print(f"  Frames/sec: {summary['current_metrics']['frames_per_second']}")

monitor.stop()
can_interface.disconnect()
```

**Generate test traffic:**
```bash
# In another terminal
while true; do
    cansend vcan0 7E0#0201000000000000
    sleep 0.01
done
```

#### Expected Results
- Monitor starts successfully
- Metrics collected every 2 seconds
- Warning logged when buffer exceeds 80%
- Frames per second calculated correctly

---

### Test 4: Message Queue Service

#### Unit Test

```bash
python -m pytest tests/test_message_queue.py -v
```

#### Manual Test

```python
# test_message_queue.py
from services.message_queue import MessageQueue, Message, MessageQueueManager
import time
import threading

# Test 1: Basic queue operations
print("Test 1: Basic Queue Operations")
queue = MessageQueue(max_size=10, name="test_queue")

# Enqueue messages
for i in range(5):
    msg = Message(
        message_type="telemetry",
        payload={"value": i},
        timestamp=time.time(),
        source="test"
    )
    queue.enqueue(msg)

print(f"Queue size: {queue.size()}")
print(f"Stats: {queue.get_stats()}")

# Dequeue messages
while not queue.is_empty():
    msg = queue.dequeue(block=False)
    if msg:
        print(f"Dequeued: {msg.message_type}, payload: {msg.payload}")

# Test 2: Queue overflow
print("\nTest 2: Queue Overflow")
small_queue = MessageQueue(max_size=3, name="small_queue")

for i in range(5):
    msg = Message(
        message_type="test",
        payload={"id": i},
        timestamp=time.time(),
        source="test"
    )
    result = small_queue.enqueue(msg, block=False)
    print(f"Enqueue {i}: {result}")

stats = small_queue.get_stats()
print(f"Dropped messages: {stats['total_dropped']}")

# Test 3: Queue Manager
print("\nTest 3: Queue Manager")
manager = MessageQueueManager()
manager.create_queue("queue1", max_size=100)
manager.create_queue("queue2", max_size=50)

all_stats = manager.get_all_stats()
for name, stats in all_stats.items():
    print(f"{name}: {stats}")
```

**Run the test:**
```bash
python test_message_queue.py
```

#### Expected Results
- Messages enqueued and dequeued correctly
- Queue overflow handled gracefully
- Statistics tracked accurately
- Queue manager handles multiple queues

---

## Testing with Simulated CAN Data

### Option 1: Using can-utils (Linux)

#### Generate Random CAN Traffic

```bash
# Generate random CAN frames
cangen vcan0 -g 10 -I 7E0 -L 8

# Generate specific OBD-II responses
# Engine RPM = 2500 RPM (0x0C)
cansend vcan0 7E8#04410C09C40000

# Coolant temp = 90°C (0x05)
cansend vcan0 7E8#03410582000000

# Vehicle speed = 65 km/h (0x0D)
cansend vcan0 7E8#03410D41000000
```

#### Replay CAN Log File

```bash
# Record CAN traffic
candump vcan0 -l

# Replay recorded traffic
canplayer -I candump-2024-01-15.log
```

### Option 2: Python CAN Simulator

```python
# can_simulator.py
import can
import time
import random

bus = can.Bus(interface='socketcan', channel='vcan0', bitrate=500000)

def send_obd2_response(pid, value):
    """Send OBD-II Mode 01 response"""
    data = [0x04, 0x41, pid, value, 0x00, 0x00, 0x00, 0x00]
    msg = can.Message(
        arbitration_id=0x7E8,
        data=data,
        is_extended_id=False
    )
    bus.send(msg)
    print(f"Sent OBD-II response: PID={hex(pid)}, Value={value}")

def send_uds_dtc_response():
    """Send UDS DTC response"""
    data = [
        0x59, 0x02, 0xFF,
        0x01, 0x03, 0x01, 0x08  # P0301
    ]
    msg = can.Message(
        arbitration_id=0x7E8,
        data=data,
        is_extended_id=False
    )
    bus.send(msg)
    print("Sent UDS DTC response")

# Simulate vehicle telemetry
print("Starting CAN simulator...")
try:
    while True:
        # Engine RPM (0x0C): 1000-4000 RPM
        rpm = random.randint(1000, 4000)
        send_obd2_response(0x0C, rpm // 4)
        
        time.sleep(1)
        
        # Vehicle speed (0x0D): 0-120 km/h
        speed = random.randint(0, 120)
        send_obd2_response(0x0D, speed)
        
        time.sleep(1)
        
        # Coolant temp (0x05): 80-100°C
        temp = random.randint(80, 100)
        send_obd2_response(0x05, temp + 40)
        
        time.sleep(1)
        
        # Occasionally send DTC
        if random.random() < 0.1:
            send_uds_dtc_response()
        
        time.sleep(2)
        
except KeyboardInterrupt:
    print("\nSimulator stopped")
    bus.shutdown()
```

**Run the simulator:**
```bash
python can_simulator.py
```

---

## Integration Testing

### End-to-End Test: CAN to Message Queue

```python
# test_integration.py
from services.can_interface import CANInterface
from services.message_queue import MessageQueue, Message
from services.uds_decoder import UDSDecoder
import time
import threading

def can_reader_thread(can_interface, queue):
    """Read CAN frames and enqueue"""
    while True:
        frame = can_interface.read_frame(timeout=1.0)
        if frame:
            msg = Message(
                message_type="can_frame",
                payload=frame.to_dict(),
                timestamp=frame.timestamp,
                source="can_interface"
            )
            queue.enqueue(msg)

def decoder_thread(queue, decoder):
    """Dequeue and decode messages"""
    while True:
        msg = queue.dequeue(timeout=1.0)
        if msg and msg.message_type == "can_frame":
            # Simulate UDS decoding
            print(f"Processing frame: {msg.payload['arbitration_id']}")

# Setup
config = {"interface": "vcan0", "bitrate": 500000, "buffer_size": 100}
can_interface = CANInterface(config)
can_interface.connect()

queue = MessageQueue(max_size=1000, name="integration_test")
decoder = UDSDecoder()

# Start threads
reader = threading.Thread(target=can_reader_thread, args=(can_interface, queue), daemon=True)
processor = threading.Thread(target=decoder_thread, args=(queue, decoder), daemon=True)

reader.start()
processor.start()

print("Integration test running for 30 seconds...")
time.sleep(30)

# Cleanup
can_interface.disconnect()
print(f"Final queue stats: {queue.get_stats()}")
```

**Run with simulated traffic:**
```bash
# Terminal 1: Start integration test
python test_integration.py

# Terminal 2: Generate CAN traffic
cangen vcan0 -g 100 -I 7E0
```

---

## Troubleshooting

### Issue: "No module named 'can'"

**Solution:**
```bash
pip install python-can
```

### Issue: "Permission denied" on CAN interface

**Solution:**
```bash
# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER

# Or run with sudo (not recommended)
sudo python test_script.py
```

### Issue: Virtual CAN interface not found

**Solution:**
```bash
# Check if vcan module is loaded
lsmod | grep vcan

# Load module if not present
sudo modprobe vcan

# Recreate interface
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

### Issue: Tests fail with "Address already in use"

**Solution:**
```bash
# Kill processes using the CAN interface
sudo pkill -f vcan0

# Reset the interface
sudo ip link set down vcan0
sudo ip link set up vcan0
```

### Issue: Import errors in tests

**Solution:**
```bash
# Ensure you're in the correct directory
cd edge-gateway

# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or install package in development mode
pip install -e .
```

### Issue: Coverage report not generated

**Solution:**
```bash
# Install coverage tools
pip install pytest-cov

# Run with explicit coverage
python -m pytest tests/ --cov=services --cov-report=term --cov-report=html
```

---

## Test Coverage Goals

- **Unit Tests**: 80% coverage minimum
- **Integration Tests**: All critical paths
- **Edge Cases**: Buffer overflow, network failures, malformed messages
- **Performance**: Frame processing rate > 1000 fps

---

## Continuous Testing

### Pre-commit Testing

Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
cd edge-gateway
python -m pytest tests/ --tb=short
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

### Automated Testing with GitHub Actions

See `.github/workflows/test.yml` for CI/CD configuration.

---

## Additional Resources

- [python-can Documentation](https://python-can.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [ISO 14229 UDS Specification](https://www.iso.org/standard/72439.html)
- [OBD-II PIDs Reference](https://en.wikipedia.org/wiki/OBD-II_PIDs)

---

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review test logs in `logs/edge-gateway.log`
3. Run tests with `-vv` flag for detailed output
4. Check CAN interface status with `ip link show`
