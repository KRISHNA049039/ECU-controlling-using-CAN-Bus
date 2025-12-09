# ECU Diagnostics System - Deployment Guide

## Prerequisites

### Required Tools
- Python 3.11+
- Node.js 18+
- AWS CLI configured with credentials
- AWS CDK CLI (`npm install -g aws-cdk`)
- Docker (for Lambda packaging)

### AWS Account Requirements
- AWS Account with appropriate permissions
- IAM user with AdministratorAccess or equivalent
- AWS CLI configured: `aws configure`

---

## Edge Gateway Deployment

### 1. Prepare Edge Device (Raspberry Pi)

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python 3.11
sudo apt-get install python3.11 python3.11-venv python3-pip -y

# Install CAN utilities
sudo apt-get install can-utils -y

# Enable CAN interface
sudo modprobe can
sudo modprobe can_raw
sudo modprobe vcan
```

### 2. Install Edge Gateway Software

```bash
# Clone repository
git clone https://github.com/KRISHNA049039/ECU-controlling-using-CAN-Bus.git
cd ECU-controlling-using-CAN-Bus/edge-gateway

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Edge Gateway

```bash
# Copy configuration template
cp config/dev.yaml config/production.yaml

# Edit configuration
nano config/production.yaml
```

Update the following fields:
- `vehicle.vin`: Your vehicle VIN
- `vehicle.gateway_id`: Unique gateway identifier
- `mqtt.endpoint`: AWS IoT Core endpoint (from CDK output)
- `mqtt.certificates`: Paths to your certificates

### 4. Provision IoT Certificates

```bash
# Create certificates using AWS IoT
aws iot create-keys-and-certificate \
    --set-as-active \
    --certificate-pem-outfile certs/device-cert.pem \
    --public-key-outfile certs/device-public-key.pem \
    --private-key-outfile certs/device-private-key.pem

# Download root CA
wget https://www.amazontrust.com/repository/AmazonRootCA1.pem \
    -O certs/AmazonRootCA1.pem

# Create IoT Thing
aws iot create-thing --thing-name "vehicle-${VIN}"

# Attach certificate to thing
aws iot attach-thing-principal \
    --thing-name "vehicle-${VIN}" \
    --principal "arn:aws:iot:region:account:cert/certificate-id"

# Attach policy to certificate
aws iot attach-policy \
    --policy-name "ECUDiagnosticsVehiclePolicy" \
    --target "arn:aws:iot:region:account:cert/certificate-id"
```

### 5. Run Edge Gateway

```bash
# Test run
python main.py --config config/production.yaml

# Run as systemd service (recommended)
sudo cp edge-gateway.service /etc/systemd/system/
sudo systemctl enable edge-gateway
sudo systemctl start edge-gateway
sudo systemctl status edge-gateway
```

---

## Cloud Infrastructure Deployment

### 1. Bootstrap CDK (First Time Only)

```bash
cd cloud-infrastructure

# Bootstrap CDK in your AWS account
cdk bootstrap aws://ACCOUNT-ID/REGION
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install CDK dependencies
pip install -r requirements.txt
```

### 3. Deploy Stacks

```bash
# Set environment variables
export CDK_DEFAULT_ACCOUNT=your-account-id
export CDK_DEFAULT_REGION=us-east-1

# Synthesize CloudFormation templates
cdk synth

# Deploy all stacks
cdk deploy --all

# Or deploy individually
cdk deploy EcuDiagnostics-IoT-dev
cdk deploy EcuDiagnostics-Storage-dev
cdk deploy EcuDiagnostics-Redshift-dev
```

### 4. Initialize Redshift Schema

```bash
# Get Redshift endpoint from CDK output
REDSHIFT_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name EcuDiagnostics-Redshift-dev \
    --query 'Stacks[0].Outputs[?OutputKey==`RedshiftClusterEndpoint`].OutputValue' \
    --output text)

# Get master password from Secrets Manager
SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name EcuDiagnostics-Redshift-dev \
    --query 'Stacks[0].Outputs[?OutputKey==`RedshiftMasterSecretArn`].OutputValue' \
    --output text)

PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id $SECRET_ARN \
    --query 'SecretString' \
    --output text | jq -r '.password')

# Connect and run schema
psql -h $REDSHIFT_ENDPOINT -U admin -d ecudiagnostics -f sql/redshift_schema.sql
```

---

## Verification

### 1. Test Edge Gateway

```bash
# Check logs
tail -f logs/edge-gateway.log

# Check CAN interface
candump can0

# Test MQTT connection
# Should see heartbeat messages every 30 seconds
```

### 2. Verify Cloud Resources

```bash
# Check IoT Core
aws iot list-things

# Check S3 buckets
aws s3 ls | grep ecu-diagnostics

# Check Redshift cluster
aws redshift describe-clusters \
    --cluster-identifier ecudiagnostics-cluster
```

### 3. Test End-to-End Flow

```bash
# Send test CAN message
cansend can0 7E8#04410C09C40000

# Check S3 for telemetry
aws s3 ls s3://ecu-diagnostics-telemetry-${ACCOUNT}/telemetry/ --recursive

# Query Redshift
psql -h $REDSHIFT_ENDPOINT -U admin -d ecudiagnostics \
    -c "SELECT COUNT(*) FROM fact_telemetry;"
```

---

## Monitoring

### CloudWatch Dashboards

```bash
# Create dashboard
aws cloudwatch put-dashboard \
    --dashboard-name ECUDiagnostics \
    --dashboard-body file://monitoring/dashboard.json
```

### CloudWatch Alarms

```bash
# Create alarms
aws cloudwatch put-metric-alarm \
    --alarm-name ECUDiagnostics-HighErrorRate \
    --alarm-description "Alert when error rate exceeds 1%" \
    --metric-name ProcessingError \
    --namespace ECUDiagnostics/Ingestion \
    --statistic Sum \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 10 \
    --comparison-operator GreaterThanThreshold
```

---

## Troubleshooting

### Edge Gateway Issues

**Problem**: Cannot connect to CAN bus
```bash
# Check CAN interface
ip link show can0

# Bring up interface
sudo ip link set can0 up type can bitrate 500000
```

**Problem**: MQTT connection fails
```bash
# Test certificates
openssl s_client -connect ${IOT_ENDPOINT}:8883 \
    -CAfile certs/AmazonRootCA1.pem \
    -cert certs/device-cert.pem \
    -key certs/device-private-key.pem
```

### Cloud Issues

**Problem**: Lambda function errors
```bash
# Check logs
aws logs tail /aws/lambda/ingestion-function --follow
```

**Problem**: Redshift connection timeout
```bash
# Check security group
aws ec2 describe-security-groups \
    --group-ids sg-xxxxx

# Update security group if needed
aws ec2 authorize-security-group-ingress \
    --group-id sg-xxxxx \
    --protocol tcp \
    --port 5439 \
    --cidr your-ip/32
```

---

## Cleanup

### Remove Cloud Resources

```bash
# Destroy all stacks
cdk destroy --all

# Or destroy individually
cdk destroy EcuDiagnostics-Redshift-dev
cdk destroy EcuDiagnostics-Storage-dev
cdk destroy EcuDiagnostics-IoT-dev
```

### Remove Edge Gateway

```bash
# Stop service
sudo systemctl stop edge-gateway
sudo systemctl disable edge-gateway

# Remove files
rm -rf /opt/ecu-diagnostics
```

---

## Production Considerations

### Security
- Use AWS Secrets Manager for all credentials
- Enable VPC endpoints for private connectivity
- Implement least-privilege IAM policies
- Enable CloudTrail for audit logging
- Use AWS WAF for API protection

### High Availability
- Deploy Redshift in multi-AZ
- Use Auto Scaling for Lambda
- Implement S3 cross-region replication
- Set up Route 53 health checks

### Cost Optimization
- Use S3 Intelligent-Tiering
- Enable Redshift pause/resume
- Implement Lambda reserved concurrency
- Use Savings Plans for predictable workloads

### Monitoring
- Set up X-Ray tracing
- Create custom CloudWatch dashboards
- Configure SNS alerts for critical metrics
- Implement log aggregation with CloudWatch Insights

---

## Support

For issues or questions:
1. Check logs: `edge-gateway/logs/` and CloudWatch Logs
2. Review documentation: `README.md`, `SYSTEM_OVERVIEW.md`, `TESTING.md`
3. Check AWS service health: https://status.aws.amazon.com/
