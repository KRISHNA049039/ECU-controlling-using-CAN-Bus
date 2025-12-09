# ECU Diagnostics System

A cloud-connected ECU diagnostics system enabling real-time vehicle telemetry streaming using CAN bus → edge gateway → AWS IoT Core.

## Architecture Overview

The system consists of three main layers:

1. **Edge Layer**: Python microservices running on edge gateway (Raspberry Pi)
   - CAN bus interface for raw frame capture
   - UDS/OBD-II protocol decoders
   - Local SQLite buffer for offline operation
   - MQTT client for AWS IoT Core connectivity

2. **Cloud Layer**: AWS serverless infrastructure
   - IoT Core for device connectivity
   - Lambda functions for data processing
   - S3 for raw data storage
   - Redshift for analytics
   - Step Functions for OTA monitoring

3. **Application Layer**: React dashboard
   - Fleet health overview
   - Real-time telemetry visualization
   - Anomaly alerts and acknowledgment
   - Predictive maintenance recommendations

## Project Structure

```
ecu-diagnostics-system/
├── edge-gateway/              # Edge gateway Python services
│   ├── config/                # Environment configurations
│   ├── services/              # Microservices (CAN, decoders, buffer, MQTT)
│   ├── tests/                 # Unit and integration tests
│   └── requirements.txt       # Python dependencies
├── cloud-infrastructure/      # AWS CDK infrastructure code
│   ├── stacks/                # CDK stack definitions
│   ├── lambdas/               # Lambda function code
│   ├── app.py                 # CDK app entry point
│   └── requirements.txt       # CDK dependencies
├── dashboard/                 # React web application
│   ├── src/                   # React components
│   ├── public/                # Static assets
│   └── package.json           # Node dependencies
└── .kiro/specs/               # Feature specifications
    └── ecu-diagnostics-system/
        ├── requirements.md    # System requirements
        ├── design.md          # Architecture design
        └── tasks.md           # Implementation tasks
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS CLI configured
- AWS CDK CLI installed
- Docker (for edge gateway deployment)

### Edge Gateway Setup

```bash
cd edge-gateway
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Cloud Infrastructure Setup

```bash
cd cloud-infrastructure
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cdk bootstrap  # First time only
```

### Dashboard Setup

```bash
cd dashboard
npm install
npm start
```

## Development

See `.kiro/specs/ecu-diagnostics-system/tasks.md` for the complete implementation plan.

## License

Proprietary - All rights reserved
