# ECU Diagnostics System - System Overview

## What This System Does

The ECU Diagnostics System is a **cloud-connected vehicle monitoring platform** that captures real-time data from a vehicle's Electronic Control Units (ECUs), processes it at the edge, streams it to AWS cloud services, and provides actionable insights through a web dashboard.

### Core Purpose

**Monitor vehicle health in real-time** by:
- Reading diagnostic data from vehicle ECUs via CAN bus
- Detecting anomalies and potential failures before they occur
- Tracking firmware updates (OTA) and their impact on vehicle performance
- Providing predictive maintenance recommendations to fleet managers

---

## High-Level System Flow

```
Vehicle CAN Bus → Edge Gateway → AWS IoT Core → Cloud Processing → Dashboard
     ↓                ↓              ↓              ↓                ↓
  ECU Data      Decode/Buffer    MQTT Pub      Store/Analyze    Visualize
```

### Step-by-Step Data Flow

1. **Vehicle generates data**: ECUs communicate over CAN bus (engine, brakes, battery, etc.)
2. **Edge gateway captures**: Raspberry Pi reads CAN frames in real-time
3. **Protocols decoded**: UDS and OBD-II messages converted to structured data
4. **Data buffered**: Local SQLite stores data during network outages
5. **Cloud transmission**: MQTT publishes telemetry to AWS IoT Core
6. **Cloud processing**: Lambda functions detect anomalies, store in S3/Redshift
7. **User visualization**: React dashboard shows health status, alerts, trends

---

## System Architecture

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Dashboard  │  │  API Gateway │  │   Cognito    │     │
│  │   (React)    │  │   (REST)     │  │   (Auth)     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                      CLOUD LAYER (AWS)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ IoT Core │→ │ Lambda   │→ │    S3    │→ │ Redshift │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       ↓             ↓              ↓              ↓          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Rules   │  │   SNS    │  │   Step   │  │ DynamoDB │   │
│  │  Engine  │  │ (Alerts) │  │Functions │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    EDGE LAYER (Gateway)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   CAN    │→ │   UDS    │→ │  Buffer  │→ │   MQTT   │   │
│  │Interface │  │ Decoder  │  │ (SQLite) │  │  Client  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       ↑             ↑              ↑              ↑          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  OBD-II  │  │  Queue   │  │ Monitor  │  │  Config  │   │
│  │ Decoder  │  │ Manager  │  │          │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
                    ┌──────────────┐
                    │  Vehicle CAN │
                    │     Bus      │
                    └──────────────┘
```

---


## Component Details

### Edge Layer Components

#### 1. CAN Interface Service (`can_interface.py`)

**What it does:**
- Connects to the vehicle's CAN bus network (the communication highway between ECUs)
- Reads raw CAN frames continuously at high speed (up to 1000+ frames/second)
- Timestamps each frame with millisecond precision for accurate event tracking
- Buffers 10,000 frames in memory to prevent data loss during processing spikes

**How it works:**
```python
# Connects to CAN bus
can_interface = CANInterface(config)
can_interface.connect()  # Opens socketcan interface

# Reads frames continuously
frame = can_interface.read_frame()
# Returns: CANFrame(id=0x7E0, data=b'\x02\x01\x00...', timestamp=1704567890.123)
```

**Real-world example:**
When you press the accelerator, the throttle position sensor sends a CAN message. The CAN interface captures this:
- **CAN ID**: `0x7E0` (Engine ECU)
- **Data**: `02 01 11 45` (Throttle at 45%)
- **Timestamp**: `1704567890.123456` (precise moment)

**Why it matters:**
Without buffering, high-speed CAN traffic (500 kbps) would overwhelm the system. The circular buffer ensures no data is lost even during processing delays.

---

#### 2. UDS Decoder Service (`uds_decoder.py`)

**What it does:**
- Decodes Unified Diagnostic Services (UDS) messages per ISO 14229 standard
- Extracts Diagnostic Trouble Codes (DTCs) like "P0301" (cylinder misfire)
- Reads ECU data identifiers (e.g., VIN, firmware version)
- Validates message format and logs errors with raw hex dumps

**How it works:**
```python
decoder = UDSDecoder()

# Raw UDS message from ECU
data = bytes([0x59, 0x02, 0xFF, 0x01, 0x03, 0x01, 0x08])

# Decode it
message = decoder.decode_message(data, ecu_address=0x7E0)

# Result:
# Service: READ_DTC_INFORMATION
# DTC: P0301 (Cylinder 1 Misfire)
# Severity: low
# Status: 0x08 (confirmed, not pending)
```

**Real-world example:**
When the check engine light comes on, the ECU has stored a DTC. The UDS decoder reads it:
- **Raw bytes**: `59 02 FF 01 03 01 08`
- **Decoded**: "P0301 - Cylinder 1 Misfire Detected"
- **Severity**: Low (not critical yet)
- **Status**: Confirmed (happened multiple times)

**Supported UDS Services:**
- **0x19**: Read DTC Information (fault codes)
- **0x22**: Read Data By Identifier (VIN, firmware version)
- **0x3E**: Tester Present (keep diagnostic session alive)

---

#### 3. OBD-II Decoder Service (`obd_decoder.py` - to be implemented)

**What it does:**
- Decodes standard OBD-II (On-Board Diagnostics) messages
- Extracts real-time engine parameters (RPM, speed, temperature)
- Converts raw hex values to engineering units (e.g., 0x09C4 → 2500 RPM)
- Polls ECU at configurable intervals (100ms to 5000ms)

**How it works:**
```python
# OBD-II request for engine RPM (PID 0x0C)
Request:  [0x01, 0x0C]

# ECU response
Response: [0x41, 0x0C, 0x09, 0xC4]

# Decoded:
# Mode: 01 (Show current data)
# PID: 0x0C (Engine RPM)
# Value: (0x09C4) / 4 = 2500 RPM
```

**Real-world example:**
Dashboard shows "Engine RPM: 2500" - here's how:
1. Gateway sends: `01 0C` (request RPM)
2. ECU responds: `41 0C 09 C4` (RPM data)
3. Decoder converts: `(9 × 256 + 196) / 4 = 2500 RPM`
4. Telemetry sent: `{"engineRpm": {"value": 2500, "unit": "rpm"}}`

**Common PIDs:**
- **0x0C**: Engine RPM
- **0x0D**: Vehicle Speed
- **0x05**: Coolant Temperature
- **0x11**: Throttle Position
- **0x2F**: Fuel Level

---

#### 4. Buffer Monitor Service (`buffer_monitor.py`)

**What it does:**
- Monitors CAN buffer utilization in real-time
- Logs warnings when buffer reaches 80% capacity
- Calculates frames per second (throughput metric)
- Tracks dropped frames and buffer statistics

**How it works:**
```python
monitor = BufferMonitor(can_interface, warning_threshold=0.8)
monitor.start(interval=5.0)  # Check every 5 seconds

# Automatically logs:
# "Buffer utilization at 85.2% (threshold: 80%)"
# "Buffer metrics: size=8520/10000, fps=1250.5"
```

**Real-world example:**
During heavy CAN traffic (e.g., rapid acceleration):
- **Normal**: 30% utilization, 500 fps
- **High load**: 85% utilization, 1200 fps → **Warning logged**
- **Overload**: 100% utilization, frames dropped → **Alert sent**

**Why it matters:**
If the buffer fills up, new CAN frames are dropped, causing data loss. The monitor provides early warning to prevent this.

---

#### 5. Message Queue Service (`message_queue.py`)

**What it does:**
- Provides thread-safe queues for passing messages between services
- Decouples CAN reading from protocol decoding (producer-consumer pattern)
- Prevents blocking when one service is slower than another
- Tracks queue statistics (enqueued, dequeued, dropped)

**How it works:**
```python
# Create queue
queue = MessageQueue(max_size=1000, name="can_to_decoder")

# Producer (CAN Interface)
frame = can_interface.read_frame()
message = Message(
    message_type="can_frame",
    payload=frame.to_dict(),
    timestamp=frame.timestamp,
    source="can_interface"
)
queue.enqueue(message)

# Consumer (UDS Decoder)
message = queue.dequeue(timeout=1.0)
decoded = uds_decoder.decode_message(message.payload['data'])
```

**Real-world example:**
CAN interface reads 1000 frames/sec, but UDS decoder processes 500 frames/sec:
- **Without queue**: CAN interface blocks, frames lost
- **With queue**: Frames buffered in queue, processed when decoder catches up

**Queue Manager:**
Manages multiple queues for different data flows:
- `can_to_uds`: CAN frames → UDS decoder
- `can_to_obd`: CAN frames → OBD-II decoder
- `decoded_to_buffer`: Decoded messages → SQLite buffer
- `buffer_to_mqtt`: Buffered batches → MQTT client

---


#### 6. Local Buffer Service (SQLite) - To Be Implemented

**What it does:**
- Stores telemetry data locally when internet connection is lost
- Batches messages (256KB or 5 seconds, whichever comes first)
- Compresses batches with gzip to save storage space
- Transmits stored data in chronological order when connection restored

**How it works:**
```python
# Network is down - buffer locally
buffer.store_batch(telemetry_batch)

# Network restored - transmit stored data
stored_batches = buffer.get_pending_batches()
for batch in stored_batches:
    mqtt_client.publish(batch)
    buffer.mark_transmitted(batch.id)
```

**Real-world example:**
Vehicle enters tunnel (no cellular signal):
1. Gateway continues collecting CAN data
2. Data stored in SQLite: `telemetry_buffer.db`
3. Storage: 1GB capacity (several hours of data)
4. Vehicle exits tunnel
5. Gateway reconnects to AWS IoT
6. Buffered data transmitted in order
7. No data loss!

---

#### 7. MQTT Client Service - To Be Implemented

**What it does:**
- Maintains secure connection to AWS IoT Core using X.509 certificates
- Publishes telemetry to topic: `vehicle/{vin}/telemetry`
- Publishes heartbeat to topic: `vehicle/{vin}/status` every 30 seconds
- Implements retry logic with exponential backoff (1s, 2s, 4s)

**How it works:**
```python
mqtt_client = MQTTClient(config)
mqtt_client.connect()

# Publish telemetry
mqtt_client.publish(
    topic="vehicle/1HGBH41JXMN109186/telemetry",
    payload=json.dumps(telemetry_data),
    qos=1  # At least once delivery
)

# Publish heartbeat
mqtt_client.publish(
    topic="vehicle/1HGBH41JXMN109186/status",
    payload=json.dumps({"status": "online", "timestamp": time.time()})
)
```

**Real-world example:**
Gateway publishes telemetry every 5 seconds:
```json
{
  "messageId": "uuid-123",
  "vin": "1HGBH41JXMN109186",
  "timestamp": "2025-01-15T10:30:45.123Z",
  "telemetryType": "obd2",
  "data": {
    "engineRpm": {"value": 2500, "unit": "rpm"},
    "vehicleSpeed": {"value": 65, "unit": "km/h"},
    "coolantTemp": {"value": 92, "unit": "celsius"}
  }
}
```

---


### Cloud Layer Components (AWS)

#### 1. AWS IoT Core

**What it does:**
- Receives MQTT messages from thousands of vehicles simultaneously
- Routes messages to different AWS services using IoT Rules
- Manages device certificates and authentication
- Provides device shadow for last known state

**IoT Rules Examples:**
```sql
-- Rule 1: Route all telemetry to Kinesis Firehose
SELECT * FROM 'vehicle/+/telemetry'

-- Rule 2: Trigger anomaly detection for critical subsystems
SELECT * FROM 'vehicle/+/telemetry' 
WHERE telemetryType IN ('engine', 'brake', 'battery')

-- Rule 3: Route OTA status updates to Step Functions
SELECT * FROM 'vehicle/+/ota/status'
```

---

#### 2. Lambda Functions

**Ingestion Lambda:**
- Validates telemetry schema
- Enriches with metadata (region, account)
- Writes raw JSON to S3
- Emits CloudWatch metrics

**Anomaly Detection Lambda:**
- Applies statistical thresholds (e.g., coolant > 105°C)
- Calculates rolling z-scores
- Loads ML models from S3
- Publishes critical alerts to SNS

**OTA Monitor Lambda:**
- Tracks firmware update progress
- Validates firmware version
- Monitors ECU performance metrics
- Triggers rollback on failure

---

#### 3. Storage Services

**Amazon S3:**
- Stores raw telemetry JSON files
- Partitioned by date and VIN: `telemetry/year=2025/month=01/day=15/vehicle={vin}/`
- Lifecycle: Glacier after 90 days
- Encrypted with AWS KMS

**Amazon Redshift:**
- Data warehouse for analytics
- Star schema: fact tables (telemetry, DTCs, anomalies) + dimension tables (vehicles)
- Optimized for time-series queries
- Powers dashboard API

**DynamoDB:**
- Stores OTA workflow state
- Tracks anomaly detection statistics
- Caches recent telemetry for fast access

---

#### 4. Step Functions (OTA Monitoring)

**What it does:**
- Orchestrates OTA firmware update workflow
- Tracks states: Initiated → Downloading → Installing → Verifying → Completed
- Monitors ECU performance during update
- Triggers rollback on failure

**State Machine:**
```
Initiated → Downloading (10 min timeout)
    ↓
Installing (5 min timeout)
    ↓
Verifying (check firmware version)
    ↓
Completed (record metrics) OR Failed (rollback)
```

---


### Application Layer Components

#### 1. API Gateway

**What it does:**
- Provides REST API for dashboard
- Authenticates requests via Cognito
- Rate limits: 1000 requests/min per user
- Routes to Lambda functions

**Endpoints:**
- `GET /vehicles` - List all vehicles with health status
- `GET /vehicles/{vin}` - Get vehicle details
- `GET /vehicles/{vin}/telemetry` - Query time-series data
- `GET /vehicles/{vin}/dtcs` - Get current fault codes
- `GET /vehicles/{vin}/anomalies` - Get anomaly history
- `POST /anomalies/{id}/acknowledge` - Acknowledge alert

---

#### 2. React Dashboard

**What it does:**
- Displays fleet overview (healthy, warning, critical, offline)
- Shows real-time telemetry charts
- Alerts on anomalies with acknowledgment
- Provides predictive maintenance recommendations

**Key Features:**
- **Fleet Overview**: Vehicle count by health status
- **Vehicle Detail**: Live telemetry, DTCs, firmware version
- **Time-Series Charts**: Engine temp, battery voltage, brake metrics
- **Alert Center**: Real-time anomaly notifications
- **Maintenance Scheduler**: Predicted failures with RUL estimates

---

#### 3. Amazon Cognito

**What it does:**
- User authentication (email/password)
- Multi-factor authentication (TOTP)
- User groups with permissions:
  - **FleetManagers**: Full access
  - **Engineers**: Read-only technical data
  - **Operators**: Alert acknowledgment only

---

## Data Flow Examples

### Example 1: Engine Overheating Detection

**Step-by-step:**

1. **Vehicle**: Coolant sensor reads 112°C
2. **CAN Bus**: ECU broadcasts: `7E0#05 41 05 98` (PID 0x05, temp = 112°C)
3. **Edge Gateway**:
   - CAN Interface captures frame
   - OBD-II Decoder extracts: `coolantTemp = 112°C`
   - Buffer stores telemetry
   - MQTT publishes to AWS
4. **AWS IoT Core**: Routes to Anomaly Detection Lambda
5. **Lambda**: Detects `112°C > 105°C threshold` → Critical anomaly
6. **SNS**: Sends alert email/SMS to fleet manager
7. **Dashboard**: Shows red alert: "Vehicle XYZ - Engine Overheating"
8. **Fleet Manager**: Acknowledges alert, dispatches technician

**Timeline**: < 2 seconds from sensor reading to alert

---

### Example 2: Cylinder Misfire Diagnosis

**Step-by-step:**

1. **Vehicle**: Engine misfires on cylinder 1
2. **ECU**: Stores DTC P0301 in memory
3. **Diagnostic Request**: Gateway sends UDS request: `19 02 FF`
4. **ECU Response**: `59 02 FF 01 03 01 08` (P0301, status confirmed)
5. **Edge Gateway**:
   - UDS Decoder extracts: DTC P0301, severity: low
   - Telemetry: `{"dtc": "P0301", "description": "Cylinder 1 Misfire"}`
6. **AWS**: Stores in Redshift `fact_dtcs` table
7. **Dashboard**: Shows DTC in vehicle detail page
8. **Predictive Maintenance**: Recommends spark plug replacement

---

### Example 3: Offline Operation & Recovery

**Step-by-step:**

1. **Vehicle enters tunnel**: No cellular signal
2. **MQTT Client**: Connection lost, retry fails
3. **Local Buffer**: Stores telemetry in SQLite
   - Batch 1: 256KB (5 seconds of data)
   - Batch 2: 256KB
   - ... continues for 10 minutes
4. **Vehicle exits tunnel**: Cellular signal restored
5. **MQTT Client**: Reconnects to AWS IoT Core
6. **Local Buffer**: Transmits 120 batches in chronological order
7. **AWS**: Processes all batches, no data loss
8. **Dashboard**: Shows complete timeline, no gaps

---


## Key Technologies & Protocols

### CAN Bus (Controller Area Network)

**What it is:**
- Vehicle communication protocol (ISO 11898)
- Multi-master broadcast bus
- Data rates: 250 kbps (low-speed) or 500 kbps (high-speed)

**How it works:**
- Each ECU broadcasts messages with unique CAN ID
- All ECUs receive all messages, filter by ID
- No central controller (peer-to-peer)

**CAN Frame Structure:**
```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│ CAN ID   │   DLC    │   Data   │   CRC    │   ACK    │
│ (11-bit) │ (4-bit)  │ (0-8 B)  │ (15-bit) │ (1-bit)  │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

**Example:**
- **CAN ID**: `0x7E0` (Engine ECU)
- **Data**: `02 01 0C 00 00 00 00 00` (Request engine RPM)

---

### UDS (Unified Diagnostic Services)

**What it is:**
- ISO 14229 standard for vehicle diagnostics
- Request-response protocol over CAN
- Used by professional diagnostic tools

**Service Types:**
- **0x10**: Diagnostic Session Control
- **0x19**: Read DTC Information (fault codes)
- **0x22**: Read Data By Identifier (VIN, firmware)
- **0x2E**: Write Data By Identifier
- **0x3E**: Tester Present (keep session alive)

**Example - Read DTCs:**
```
Request:  [0x19, 0x02, 0xFF]  # Read all DTCs
Response: [0x59, 0x02, 0xFF, 0x01, 0x03, 0x01, 0x08]
          # Service 0x19, sub 0x02, DTC: P0301, status: 0x08
```

---

### OBD-II (On-Board Diagnostics)

**What it is:**
- Standardized vehicle diagnostic interface (SAE J1979)
- Mandatory in US vehicles since 1996
- Provides real-time engine data

**Modes:**
- **Mode 01**: Show current data (live parameters)
- **Mode 02**: Show freeze frame data
- **Mode 03**: Show stored DTCs
- **Mode 04**: Clear DTCs
- **Mode 09**: Request vehicle information

**PIDs (Parameter IDs):**
- **0x0C**: Engine RPM
- **0x0D**: Vehicle Speed
- **0x05**: Coolant Temperature
- **0x11**: Throttle Position

**Example - Read RPM:**
```
Request:  [0x01, 0x0C]           # Mode 01, PID 0x0C
Response: [0x41, 0x0C, 0x09, 0xC4]  # RPM = (0x09C4) / 4 = 2500
```

---

### MQTT (Message Queuing Telemetry Transport)

**What it is:**
- Lightweight pub/sub messaging protocol
- Designed for IoT devices with limited bandwidth
- QoS levels: 0 (at most once), 1 (at least once), 2 (exactly once)

**Topic Structure:**
```
vehicle/{vin}/telemetry    # Telemetry data
vehicle/{vin}/status       # Gateway heartbeat
vehicle/{vin}/ota/status   # OTA update progress
```

**Example:**
```python
# Publish telemetry
client.publish(
    topic="vehicle/1HGBH41JXMN109186/telemetry",
    payload=json.dumps(telemetry),
    qos=1  # At least once delivery
)
```

---


## Anomaly Detection

### Statistical Threshold Detection

**How it works:**
- Compares telemetry values against predefined thresholds
- Generates alerts when thresholds exceeded
- Fast detection (< 2 seconds)

**Thresholds:**
- **Coolant Temperature**: > 105°C → Critical
- **Battery Voltage**: < 11.5V or > 15.5V → Critical
- **Engine RPM**: > 6000 RPM → Warning
- **Brake Pressure**: < 20 PSI → Critical

**Example:**
```python
if coolant_temp > 105:
    severity_score = 95
    alert = {
        "type": "temperature_spike",
        "severity": "critical",
        "message": "Engine coolant temperature critical: 112°C"
    }
    sns.publish(alert)
```

---

### Machine Learning-Based Detection

**How it works:**
- Trains Isolation Forest models on historical data
- Detects subtle anomalies that thresholds miss
- Identifies patterns like gradual degradation

**Models:**
- **Engine Model**: RPM, temp, oil pressure, throttle
- **Brake Model**: Pressure, pad wear, ABS events
- **Battery Model**: Voltage, current, temperature

**Example:**
```python
# Load trained model
model = load_model("s3://models/engine/isolation_forest_v1.pkl")

# Score incoming telemetry
features = [rpm, coolant_temp, oil_pressure, throttle]
anomaly_score = model.decision_function([features])[0]

if anomaly_score > 0.7:
    # Anomaly detected
    create_anomaly_event(score=anomaly_score)
```

**Use Cases:**
- Detect gradual coolant temperature increase (not sudden spike)
- Identify unusual RPM patterns during acceleration
- Predict battery failure before voltage drops

---

### Rolling Z-Score Analysis

**How it works:**
- Calculates z-score over 7-day rolling window
- Detects deviations from normal behavior
- Adapts to vehicle-specific patterns

**Formula:**
```
z-score = (current_value - mean) / std_dev
```

**Example:**
```python
# Brake pressure history (7 days)
brake_pressures = [45, 46, 44, 45, 47, 46, 45, ...]

mean = np.mean(brake_pressures)  # 45.5 PSI
std_dev = np.std(brake_pressures)  # 1.2 PSI

current_pressure = 38  # Current reading
z_score = (38 - 45.5) / 1.2 = -6.25  # Significant deviation!

if abs(z_score) > 3:
    # Anomaly: brake pressure unusually low
    alert("Brake system anomaly detected")
```

---


## Predictive Maintenance

### How It Works

**Data Collection:**
1. Continuous telemetry from vehicle sensors
2. Historical failure data from maintenance records
3. Environmental factors (temperature, humidity, terrain)

**Analysis:**
1. **Trend Analysis**: Identify degradation patterns
2. **RUL Calculation**: Remaining Useful Life estimation
3. **Failure Prediction**: Probability of failure within timeframe
4. **Priority Scoring**: Urgency × Safety Impact × Repair Cost

**Example - Brake Pad Prediction:**
```python
# Historical brake pad wear data
wear_history = [
    {"date": "2024-01-01", "thickness": 10.0},  # mm
    {"date": "2024-02-01", "thickness": 9.5},
    {"date": "2024-03-01", "thickness": 9.0},
    {"date": "2024-04-01", "thickness": 8.4},
]

# Calculate wear rate
wear_rate = 0.2 mm/month  # Linear regression

# Current thickness
current_thickness = 8.4 mm

# Minimum safe thickness
min_thickness = 3.0 mm

# Remaining useful life
rul = (current_thickness - min_thickness) / wear_rate
rul = 27 months

# Prediction
if rul < 2:  # Less than 2 months
    recommendation = {
        "component": "Brake Pads",
        "action": "Replace within 2 months",
        "confidence": 0.85,
        "priority_score": 75  # High priority
    }
```

**Dashboard Display:**
```
┌─────────────────────────────────────────────────────┐
│ Predictive Maintenance Recommendations              │
├─────────────────────────────────────────────────────┤
│ Vehicle: 1HGBH41JXMN109186                         │
│                                                      │
│ ⚠️  Brake Pads - Replace within 2 months           │
│     Confidence: 85%                                 │
│     Priority: High (75/100)                         │
│     Estimated Cost: $150                            │
│                                                      │
│ ⚠️  Battery - Replace within 6 months              │
│     Confidence: 72%                                 │
│     Priority: Medium (60/100)                       │
│     Estimated Cost: $200                            │
└─────────────────────────────────────────────────────┘
```

---

## OTA (Over-The-Air) Update Monitoring

### Workflow

**1. Initiation:**
- Fleet manager triggers OTA update via dashboard
- Step Function workflow created
- Baseline ECU metrics captured

**2. Downloading:**
- Firmware downloaded to vehicle
- Progress tracked: 0% → 100%
- Timeout: 10 minutes

**3. Installing:**
- ECU installs new firmware
- Vehicle may reboot
- Timeout: 5 minutes

**4. Verifying:**
- Check firmware version matches expected
- Monitor ECU performance metrics
- Compare to baseline

**5. Completion:**
- Record success metrics
- Update vehicle firmware version in database
- Notify fleet manager

**6. Failure Handling:**
- Capture error logs
- Trigger automatic rollback
- Alert engineering team

**Performance Monitoring:**
```python
# Baseline metrics (before OTA)
baseline = {
    "cpu_utilization": 35,
    "memory_usage": 45,
    "response_time": 80  # ms
}

# Post-OTA metrics
current = {
    "cpu_utilization": 55,  # +57% increase
    "memory_usage": 48,
    "response_time": 120  # +50% increase
}

# Check for performance degradation
if current["response_time"] > baseline["response_time"] * 1.5:
    # Performance anomaly detected
    alert("OTA update caused performance degradation")
    trigger_rollback()
```

---


## Security & Authentication

### Edge Gateway Security

**Certificate-Based Authentication:**
- Each gateway has unique X.509 certificate
- Private key stored securely on device
- Mutual TLS authentication with AWS IoT Core

**Data Encryption:**
- MQTT over TLS (port 8883)
- AES-256 encryption for local SQLite database
- Encrypted storage for certificates

---

### Cloud Security

**AWS IoT Policies:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["iot:Publish"],
      "Resource": ["arn:aws:iot:region:account:topic/vehicle/${iot:ClientId}/*"]
    }
  ]
}
```
- Restricts each device to publish only to its own topics
- Prevents cross-vehicle data access

**S3 Encryption:**
- Server-side encryption with AWS KMS
- Bucket policies restrict access
- Versioning enabled for audit trail

**Cognito Authentication:**
- Password policy: 12+ characters, complexity requirements
- Optional MFA (TOTP)
- Session timeout: 1 hour
- Role-based access control (RBAC)

---

## Performance Characteristics

### Edge Gateway

**Throughput:**
- CAN frame processing: 1000+ frames/second
- Buffer capacity: 10,000 frames in memory
- Local storage: 1 GB (several hours of data)

**Latency:**
- CAN frame to decoded telemetry: < 10 ms
- Telemetry to MQTT publish: < 100 ms
- End-to-end (CAN to AWS): < 500 ms

**Resource Usage:**
- CPU: 20-40% (Raspberry Pi 4)
- Memory: 200-400 MB
- Storage: 50 MB/hour (compressed)

---

### Cloud Processing

**Scalability:**
- Supports 10,000+ concurrent vehicles
- IoT Core: 1,000,000 messages/second
- Lambda: Auto-scales to demand
- Redshift: Petabyte-scale analytics

**Latency:**
- IoT Core to Lambda: < 100 ms
- Anomaly detection: < 2 seconds
- Alert delivery: < 5 seconds
- Dashboard refresh: 30 seconds

**Storage:**
- S3: Unlimited capacity
- Redshift: 2 TB (expandable)
- DynamoDB: Auto-scaling

---

## Monitoring & Observability

### CloudWatch Dashboards

**Edge Gateway Metrics:**
- Buffer utilization
- MQTT connection status
- Frames per second
- Dropped frame count

**Lambda Metrics:**
- Invocation count
- Error rate
- Duration (p50, p95, p99)
- Throttles

**Redshift Metrics:**
- Query performance
- Storage utilization
- Connection count

**API Gateway Metrics:**
- Request count
- Latency (p50, p95, p99)
- 4xx/5xx error rates

---

### CloudWatch Alarms

**Critical Alarms:**
- Lambda error rate > 1%
- Redshift load failures > 0.1%
- API Gateway 5xx errors
- IoT Core disconnections

**Warning Alarms:**
- Buffer utilization > 80%
- High CAN frame drop rate
- Slow query performance
- High API latency

---

### X-Ray Tracing

**Distributed Tracing:**
```
Vehicle → IoT Core → Lambda → S3 → Redshift
  ↓         ↓          ↓       ↓       ↓
 50ms     100ms      200ms   150ms   500ms
```

**Use Cases:**
- Identify bottlenecks in data pipeline
- Debug failed requests
- Optimize Lambda performance
- Trace anomaly detection flow

---


## Use Cases

### Use Case 1: Fleet Management

**Scenario:** Transportation company with 500 delivery trucks

**Benefits:**
- Real-time visibility into entire fleet health
- Reduce unplanned downtime by 40%
- Optimize maintenance schedules
- Lower maintenance costs by 25%

**Dashboard View:**
```
Fleet Overview: 500 vehicles
├── Healthy: 450 (90%)
├── Warning: 35 (7%)
├── Critical: 10 (2%)
└── Offline: 5 (1%)

Critical Alerts:
- Truck #237: Engine overheating (112°C)
- Truck #089: Battery voltage low (10.8V)
- Truck #412: Brake system anomaly
```

---

### Use Case 2: Predictive Maintenance

**Scenario:** Prevent brake failure before it happens

**Process:**
1. Monitor brake pad thickness via telemetry
2. Track wear rate over time
3. Predict when pads reach minimum thickness
4. Schedule maintenance 2 weeks in advance
5. Avoid emergency repairs and downtime

**ROI:**
- Emergency repair cost: $800 (towing + labor)
- Scheduled maintenance: $150
- Savings per vehicle: $650
- Fleet of 500 vehicles: $325,000/year saved

---

### Use Case 3: Warranty Claims

**Scenario:** Manufacturer needs proof of defect

**Benefits:**
- Complete telemetry history for warranty period
- Prove defect vs. misuse
- Identify systemic issues across fleet
- Reduce fraudulent claims

**Example:**
```
Claim: Engine failure at 50,000 miles
Evidence from telemetry:
- Coolant temperature consistently > 110°C
- Oil pressure warnings ignored
- Maintenance intervals exceeded
Result: Claim denied (customer misuse)
```

---

### Use Case 4: Recall Management

**Scenario:** Manufacturer issues recall for ECU firmware bug

**Process:**
1. Identify affected vehicles by firmware version
2. Push OTA update to all affected vehicles
3. Monitor update success rate
4. Track ECU performance post-update
5. Verify bug fix effectiveness

**Metrics:**
- Vehicles affected: 10,000
- OTA success rate: 98.5%
- Update time: 15 minutes per vehicle
- Cost savings vs. dealer visits: $5,000,000

---

## Future Enhancements

### Phase 2 Features

**Advanced Analytics:**
- Driver behavior scoring (harsh braking, rapid acceleration)
- Fuel efficiency optimization recommendations
- Route optimization based on vehicle health

**Enhanced Predictions:**
- Deep learning models for failure prediction
- Multi-component failure correlation
- Seasonal pattern recognition

**Integration:**
- Telematics system integration
- ERP system integration for parts ordering
- Mobile app for drivers

---

### Phase 3 Features

**Edge AI:**
- On-device anomaly detection (reduce cloud costs)
- Real-time driver assistance
- Offline predictive maintenance

**Advanced Diagnostics:**
- Remote ECU reprogramming
- Advanced fault isolation
- Automated diagnostic workflows

**Fleet Optimization:**
- Predictive routing based on vehicle health
- Dynamic maintenance scheduling
- Cross-fleet benchmarking

---

## Glossary

**CAN Bus**: Controller Area Network - vehicle communication protocol  
**ECU**: Electronic Control Unit - embedded computer in vehicle  
**DTC**: Diagnostic Trouble Code - standardized fault code (e.g., P0301)  
**UDS**: Unified Diagnostic Services - ISO 14229 diagnostic protocol  
**OBD-II**: On-Board Diagnostics II - standardized diagnostic interface  
**PID**: Parameter ID - specific data parameter in OBD-II  
**VIN**: Vehicle Identification Number - unique 17-character identifier  
**OTA**: Over-The-Air - wireless firmware update  
**RUL**: Remaining Useful Life - predicted time until component failure  
**MQTT**: Message Queuing Telemetry Transport - IoT messaging protocol  
**QoS**: Quality of Service - message delivery guarantee level  
**TLS**: Transport Layer Security - encryption protocol  
**Lambda**: AWS serverless compute service  
**S3**: Amazon Simple Storage Service - object storage  
**Redshift**: Amazon data warehouse service  
**IoT Core**: AWS managed IoT platform  
**Step Functions**: AWS workflow orchestration service  
**SNS**: Simple Notification Service - pub/sub messaging  
**Cognito**: AWS authentication and authorization service

---

## Quick Reference

### Common CAN IDs
- `0x7E0`: Engine ECU (request)
- `0x7E8`: Engine ECU (response)
- `0x7E1`: Transmission ECU (request)
- `0x7E9`: Transmission ECU (response)

### Common OBD-II PIDs
- `0x0C`: Engine RPM
- `0x0D`: Vehicle Speed
- `0x05`: Coolant Temperature
- `0x11`: Throttle Position
- `0x2F`: Fuel Level
- `0x0F`: Intake Air Temperature

### Common DTC Prefixes
- `P`: Powertrain (engine, transmission)
- `C`: Chassis (ABS, suspension)
- `B`: Body (airbags, climate control)
- `U`: Network (communication errors)

### UDS Services
- `0x10`: Diagnostic Session Control
- `0x19`: Read DTC Information
- `0x22`: Read Data By Identifier
- `0x2E`: Write Data By Identifier
- `0x3E`: Tester Present

---

## Support & Documentation

**Additional Resources:**
- [TESTING.md](TESTING.md) - Comprehensive testing guide
- [README.md](README.md) - Project setup and getting started
- [Design Document](.kiro/specs/ecu-diagnostics-system/design.md) - Detailed architecture
- [Requirements](.kiro/specs/ecu-diagnostics-system/requirements.md) - System requirements
- [Tasks](.kiro/specs/ecu-diagnostics-system/tasks.md) - Implementation plan

**External References:**
- [ISO 14229 UDS Specification](https://www.iso.org/standard/72439.html)
- [SAE J1979 OBD-II Standard](https://www.sae.org/standards/content/j1979_202104/)
- [python-can Documentation](https://python-can.readthedocs.io/)
- [AWS IoT Core Documentation](https://docs.aws.amazon.com/iot/)

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-15  
**Status:** Active Development
