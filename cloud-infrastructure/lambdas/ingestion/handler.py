"""
Telemetry Ingestion Lambda Handler

Validates, enriches, and stores incoming telemetry from IoT Core.
"""
import json
import boto3
import os
from datetime import datetime
from typing import Dict, Any
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

# Environment variables
S3_BUCKET = os.environ.get('S3_BUCKET')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')


def lambda_handler(event, context):
    """
    Lambda handler for telemetry ingestion
    
    Args:
        event: IoT Core message event
        context: Lambda context
        
    Returns:
        Response dictionary
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Validate message schema
        if not validate_schema(event):
            logger.error("Invalid message schema")
            emit_metric("ValidationFailure", 1)
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid schema'})
            }
        
        # Enrich message with metadata
        enriched_message = enrich_message(event)
        
        # Write to S3
        s3_key = generate_s3_key(enriched_message)
        write_to_s3(enriched_message, s3_key)
        
        # Emit metrics
        emit_metric("MessageProcessed", 1)
        emit_metric("MessageSize", len(json.dumps(enriched_message)))
        
        logger.info(f"Successfully processed message: {s3_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Success', 's3_key': s3_key})
        }
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        emit_metric("ProcessingError", 1)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def validate_schema(message: Dict[str, Any]) -> bool:
    """
    Validate message schema
    
    Args:
        message: Message to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['messageId', 'vin', 'timestamp', 'telemetryType']
    
    for field in required_fields:
        if field not in message:
            logger.warning(f"Missing required field: {field}")
            return False
    
    # Validate VIN format (17 characters)
    if len(message.get('vin', '')) != 17:
        logger.warning(f"Invalid VIN format: {message.get('vin')}")
        return False
    
    return True


def enrich_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich message with metadata
    
    Args:
        message: Original message
        
    Returns:
        Enriched message
    """
    enriched = message.copy()
    
    # Add ingestion metadata
    enriched['metadata'] = {
        'ingestion_timestamp': datetime.utcnow().isoformat(),
        'region': AWS_REGION,
        'lambda_request_id': context.aws_request_id if 'context' in globals() else 'unknown'
    }
    
    return enriched


def generate_s3_key(message: Dict[str, Any]) -> str:
    """
    Generate S3 key for message
    
    Args:
        message: Message to store
        
    Returns:
        S3 key path
    """
    timestamp = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
    vin = message['vin']
    message_id = message['messageId']
    
    key = (
        f"telemetry/"
        f"year={timestamp.year}/"
        f"month={timestamp.month:02d}/"
        f"day={timestamp.day:02d}/"
        f"vehicle={vin}/"
        f"{timestamp.isoformat()}-{message_id}.json"
    )
    
    return key


def write_to_s3(message: Dict[str, Any], s3_key: str) -> None:
    """
    Write message to S3
    
    Args:
        message: Message to write
        s3_key: S3 key path
    """
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=json.dumps(message),
        ContentType='application/json',
        ServerSideEncryption='aws:kms'
    )
    
    logger.info(f"Wrote message to s3://{S3_BUCKET}/{s3_key}")


def emit_metric(metric_name: str, value: float) -> None:
    """
    Emit CloudWatch metric
    
    Args:
        metric_name: Metric name
        value: Metric value
    """
    try:
        cloudwatch.put_metric_data(
            Namespace='ECUDiagnostics/Ingestion',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                }
            ]
        )
    except Exception as e:
        logger.warning(f"Failed to emit metric {metric_name}: {e}")
