# Requirements Document

## Introduction

This document specifies the requirements for a cloud-connected ECU diagnostics system that enables real-time vehicle telemetry streaming from CAN bus networks through an edge gateway to AWS IoT Core. The system decodes automotive diagnostic protocols (UDS, OBD-II), stores structured telemetry data, monitors OTA firmware updates, detects subsystem anomalies, and provides visualization dashboards for ECU health monitoring and predictive maintenance.

## Glossary

- **ECU**: Electronic Control Unit - embedded system in vehicles that controls electrical subsystems
- **CAN Bus**: Controller Area Network - vehicle communication protocol for ECU intercommunication
- **UDS**: Unified Diagnostic Services (ISO 14229) - diagnostic communication protocol
- **DTC**: Diagnostic Trouble Code - standardized error codes from vehicle systems
- **OBD-II**: On-Board Diagnostics II - standardized vehicle diagnostic interface
- **PID**: Parameter ID - specific data parameter in OBD-II protocol
- **Edge Gateway**: Local computing device that processes CAN bus data before cloud transmission
- **Telemetry System**: The complete ECU diagnostics system being specified
- **OTA**: Over-The-Air - wireless firmware update mechanism
- **Anomaly Detection Module**: Component that identifies abnormal patterns in vehicle subsystem data
- **Dashboard Service**: Web-based visualization interface for ECU health monitoring

## Requirements

### Requirement 1: CAN Bus Data Acquisition

**User Story:** As a vehicle diagnostics engineer, I want to capture raw CAN bus messages from the vehicle network, so that I can monitor all ECU communications in real-time.

#### Acceptance Criteria

1. THE Edge Gateway SHALL interface with the vehicle CAN bus network to receive raw CAN frames
2. WHEN a CAN frame is received, THE Edge Gateway SHALL timestamp the frame with millisecond precision
3. THE Edge Gateway SHALL buffer CAN frames with a minimum capacity of 10,000 messages
4. WHEN the buffer reaches 80% capacity, THE Edge Gateway SHALL log a warning event
5. THE Edge Gateway SHALL support CAN bus data rates of 250 kbps and 500 kbps

### Requirement 2: UDS Protocol Decoding

**User Story:** As a diagnostics engineer, I want to decode UDS diagnostic messages according to ISO 14229, so that I can extract meaningful diagnostic information from ECU responses.

#### Acceptance Criteria

1. WHEN a UDS diagnostic request is transmitted, THE Telemetry System SHALL decode the service identifier and sub-function
2. THE Telemetry System SHALL parse UDS response messages for services 0x19 (Read DTC Information), 0x22 (Read Data By Identifier), and 0x3E (Tester Present)
3. WHEN a DTC is retrieved via UDS service 0x19, THE Telemetry System SHALL extract the DTC code, status byte, and severity level
4. THE Telemetry System SHALL validate UDS message format compliance with ISO 14229 specification
5. WHEN an invalid UDS message is detected, THE Telemetry System SHALL log the error with the raw message payload

### Requirement 3: OBD-II Data Extraction

**User Story:** As a fleet manager, I want to collect standard OBD-II parameters from vehicles, so that I can monitor engine performance and emissions data across my fleet.

#### Acceptance Criteria

1. THE Telemetry System SHALL decode OBD-II Mode 01 PIDs for real-time engine data
2. THE Telemetry System SHALL extract at minimum the following PIDs: engine RPM (0x0C), vehicle speed (0x0D), coolant temperature (0x05), throttle position (0x11), and fuel level (0x2F)
3. WHEN an OBD-II PID response is received, THE Telemetry System SHALL apply the standard conversion formula to produce human-readable values with correct units
4. THE Telemetry System SHALL decode OBD-II Mode 03 to retrieve stored DTCs
5. THE Telemetry System SHALL poll OBD-II PIDs at a configurable interval between 100ms and 5000ms

### Requirement 4: Edge Gateway Processing

**User Story:** As a system architect, I want the edge gateway to preprocess and structure CAN data locally, so that I can reduce cloud bandwidth costs and enable offline operation.

#### Acceptance Criteria

1. THE Edge Gateway SHALL decode CAN frames into structured JSON telemetry messages
2. THE Edge Gateway SHALL aggregate telemetry data into batches with a maximum size of 256 KB or 5-second time window, whichever occurs first
3. WHEN network connectivity is unavailable, THE Edge Gateway SHALL store telemetry batches locally with a maximum storage capacity of 1 GB
4. WHEN connectivity is restored, THE Edge Gateway SHALL transmit stored telemetry batches in chronological order
5. THE Edge Gateway SHALL compress telemetry batches using gzip compression before transmission

### Requirement 5: AWS IoT Core Integration

**User Story:** As a cloud engineer, I want to stream vehicle telemetry to AWS IoT Core securely, so that I can leverage AWS services for storage and analytics.

#### Acceptance Criteria

1. THE Edge Gateway SHALL establish secure MQTT connections to AWS IoT Core using X.509 certificates
2. THE Edge Gateway SHALL publish telemetry messages to device-specific MQTT topics following the pattern `vehicle/{vin}/telemetry`
3. WHEN an MQTT publish fails, THE Edge Gateway SHALL retry transmission with exponential backoff up to 3 attempts
4. THE Telemetry System SHALL maintain MQTT connection keep-alive with a 60-second interval
5. THE Edge Gateway SHALL publish connection status messages to the topic `vehicle/{vin}/status` every 30 seconds

### Requirement 6: Telemetry Data Storage

**User Story:** As a data analyst, I want vehicle telemetry stored in queryable formats, so that I can perform historical analysis and generate reports.

#### Acceptance Criteria

1. THE Telemetry System SHALL store raw telemetry messages in Amazon S3 with partitioning by date and vehicle identifier
2. THE Telemetry System SHALL transform and load structured telemetry data into Amazon Redshift within 5 minutes of ingestion
3. THE Telemetry System SHALL create Redshift tables for DTCs, OBD-II parameters, and UDS diagnostic sessions
4. THE Telemetry System SHALL retain S3 raw data for a minimum of 90 days
5. WHEN telemetry data is written to S3, THE Telemetry System SHALL apply server-side encryption using AWS KMS

### Requirement 7: OTA Update Monitoring

**User Story:** As a firmware engineer, I want to track OTA firmware update progress and outcomes, so that I can ensure successful ECU updates and identify failures quickly.

#### Acceptance Criteria

1. WHEN an OTA update is initiated, THE Telemetry System SHALL create a workflow execution in AWS Step Functions
2. THE Telemetry System SHALL track OTA update states: initiated, downloading, installing, verifying, completed, and failed
3. WHEN an ECU reports update progress, THE Telemetry System SHALL update the workflow state via AWS Lambda
4. THE Telemetry System SHALL record ECU firmware version before and after OTA updates
5. WHEN an OTA update fails, THE Telemetry System SHALL capture the failure reason and ECU error logs

### Requirement 8: ECU Performance Monitoring

**User Story:** As a vehicle engineer, I want to monitor ECU performance metrics during and after OTA updates, so that I can detect firmware-related performance degradation.

#### Acceptance Criteria

1. THE Telemetry System SHALL collect ECU CPU utilization, memory usage, and response time metrics
2. THE Telemetry System SHALL establish baseline performance metrics for each ECU type during normal operation
3. WHEN ECU response time exceeds baseline by 50%, THE Telemetry System SHALL generate a performance anomaly event
4. THE Telemetry System SHALL correlate performance anomalies with recent OTA update events within a 24-hour window
5. THE Telemetry System SHALL track ECU reset events and associate them with firmware versions

### Requirement 9: Anomaly Detection for Vehicle Subsystems

**User Story:** As a predictive maintenance engineer, I want to detect abnormal patterns in engine, braking, and battery data, so that I can predict failures before they occur.

#### Acceptance Criteria

1. THE Anomaly Detection Module SHALL apply statistical threshold analysis to engine RPM, coolant temperature, and oil pressure parameters
2. WHEN engine coolant temperature exceeds 105°C, THE Anomaly Detection Module SHALL generate a critical anomaly alert
3. THE Anomaly Detection Module SHALL calculate rolling z-scores for brake pressure and pad wear indicators over a 7-day window
4. WHEN battery voltage drops below 11.5V or exceeds 15.5V, THE Anomaly Detection Module SHALL generate a battery anomaly alert
5. THE Anomaly Detection Module SHALL assign anomaly severity scores from 0 to 100 based on deviation magnitude and parameter criticality

### Requirement 10: Machine Learning-Based Anomaly Scoring

**User Story:** As a data scientist, I want to apply ML models to detect complex anomaly patterns, so that I can identify subtle degradation trends that statistical methods miss.

#### Acceptance Criteria

1. THE Anomaly Detection Module SHALL train isolation forest models on historical telemetry data for each vehicle subsystem
2. THE Anomaly Detection Module SHALL generate anomaly scores for incoming telemetry using trained ML models
3. WHEN an ML anomaly score exceeds 0.7, THE Anomaly Detection Module SHALL create an anomaly event record
4. THE Anomaly Detection Module SHALL retrain ML models weekly using the most recent 30 days of telemetry data
5. THE Anomaly Detection Module SHALL track model performance metrics including false positive rate and detection latency

### Requirement 11: Real-Time Alerting

**User Story:** As a fleet operations manager, I want to receive immediate alerts for critical vehicle issues, so that I can take corrective action before safety is compromised.

#### Acceptance Criteria

1. WHEN a critical anomaly is detected, THE Telemetry System SHALL publish an alert message to an SNS topic within 2 seconds
2. THE Telemetry System SHALL support alert delivery via email, SMS, and webhook endpoints
3. THE Telemetry System SHALL include vehicle identifier, anomaly type, severity, and affected subsystem in alert messages
4. THE Telemetry System SHALL suppress duplicate alerts for the same anomaly within a 15-minute window
5. WHEN an alert is acknowledged by an operator, THE Telemetry System SHALL record the acknowledgment timestamp and operator identity

### Requirement 12: ECU Health Dashboard

**User Story:** As a fleet manager, I want to view ECU health status across my vehicle fleet, so that I can prioritize maintenance activities and monitor overall fleet health.

#### Acceptance Criteria

1. THE Dashboard Service SHALL display a fleet overview showing the count of vehicles by health status: healthy, warning, critical, and offline
2. THE Dashboard Service SHALL provide a vehicle detail view showing current DTC codes, anomaly alerts, and key OBD-II parameters
3. THE Dashboard Service SHALL render time-series charts for engine temperature, battery voltage, and brake system metrics over selectable time ranges
4. THE Dashboard Service SHALL refresh dashboard data automatically every 30 seconds
5. THE Dashboard Service SHALL allow filtering vehicles by location, model, firmware version, and health status

### Requirement 13: Predictive Maintenance Insights

**User Story:** As a maintenance planner, I want to see predictive maintenance recommendations, so that I can schedule service appointments proactively.

#### Acceptance Criteria

1. THE Dashboard Service SHALL display a list of vehicles with predicted maintenance needs within the next 30 days
2. THE Dashboard Service SHALL show the predicted failure component, confidence score, and recommended action for each maintenance prediction
3. THE Dashboard Service SHALL calculate remaining useful life estimates for brake pads, battery, and engine oil based on telemetry trends
4. THE Dashboard Service SHALL provide a maintenance priority score combining urgency, safety impact, and repair cost
5. THE Dashboard Service SHALL allow exporting maintenance recommendations as CSV reports

### Requirement 14: Historical Trend Analysis

**User Story:** As a vehicle engineer, I want to analyze historical trends for specific parameters, so that I can identify long-term degradation patterns and validate engineering changes.

#### Acceptance Criteria

1. THE Dashboard Service SHALL allow querying historical telemetry data for any vehicle and parameter combination
2. THE Dashboard Service SHALL render trend charts comparing parameter values before and after OTA updates
3. THE Dashboard Service SHALL calculate and display statistical summaries including mean, median, standard deviation, and percentiles
4. THE Dashboard Service SHALL support overlaying multiple vehicles on the same trend chart for comparative analysis
5. THE Dashboard Service SHALL allow exporting chart data and statistical summaries in JSON and CSV formats
