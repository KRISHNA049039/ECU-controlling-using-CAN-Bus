"""
Anomaly Detection Lambda Handler

Detects anomalies in vehicle telemetry using statistical thresholds and ML models.
"""
import json
import boto3
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns_client = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')

# Environment variables
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
STATS_TABLE = os.environ.get('STATS_TABLE', 'anomaly_statistics')

# Thresholds configuration
THRESHOLDS = {
    'coolant_temp': {'max': 105, 'unit': 'celsius', 'severity': 'critical'},
    'battery_voltage': {'min': 11.5, 'max': 15.5, 'unit': 'volts', 'severity': 'critical'},
    'engine_rpm': {'max': 6000, 'unit': 'rpm', 'severity': 'warning'},
    'oil_pressure': {'min': 20, 'unit': 'psi', 'severity': 'critical'}
}


def lambda_handler(event, context):
    """
    Lambda handler for anomaly detection
    
    Args:
        event: Telemetry message from IoT Core
        context: Lambda context
        
    Returns:
        Response dictionary
    """
    try:
        logger.info(f"Processing telemetry for anomaly detection")
        
        # Extract telemetry data
        telemetry = event
        vin = telemetry.get('vin')
        telemetry_type = telemetry.get('telemetryType')
        data = telemetry.get('data', {})
        
        # Check if this is relevant telemetry
        if telemetry_type not in ['obd2', 'engine', 'brake', 'battery']:
            logger.info(f"Skipping telemetry type: {telemetry_type}")
            return {'statusCode': 200, 'body': 'Skipped'}
        
        anomalies = []
        
        # Statistical threshold detection
        threshold_anomalies = detect_threshold_anomalies(vin, data, telemetry)
        anomalies.extend(threshold_anomalies)
        
        # Z-score detection
        zscore_anomalies = detect_zscore_anomalies(vin, data, telemetry)
        anomalies.extend(zscore_anomalies)
        
        # Process anomalies
        for anomaly in anomalies:
            # Calculate severity score
            severity_score = calculate_severity_score(anomaly)
            anomaly['severity_score'] = severity_score
            
            # Publish critical anomalies
            if severity_score >= 80:
                publish_alert(anomaly)
        
        logger.info(f"Detected {len(anomalies)} anomalies for VIN {vin}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'anomalies_detected': len(anomalies),
                'critical_anomalies': sum(1 for a in anomalies if a['severity_score'] >= 80)
            })
        }
        
    except Exception as e:
        logger.error(f"Error in anomaly detection: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def detect_threshold_anomalies(vin: str, data: Dict[str, Any], telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Detect anomalies using statistical thresholds
    
    Args:
        vin: Vehicle identification number
        data: Telemetry data
        telemetry: Full telemetry message
        
    Returns:
        List of detected anomalies
    """
    anomalies = []
    
    # Check OBD-II parameters
    if 'parameters' in data:
        for param in data['parameters']:
            param_name = param.get('name')
            param_value = param.get('value')
            
            if param_name in THRESHOLDS:
                threshold = THRESHOLDS[param_name]
                
                # Check max threshold
                if 'max' in threshold and param_value > threshold['max']:
                    anomalies.append({
                        'vin': vin,
                        'timestamp': telemetry.get('timestamp'),
                        'subsystem': get_subsystem(param_name),
                        'anomaly_type': f'{param_name}_high',
                        'detection_method': 'statistical_threshold',
                        'parameters': {
                            param_name: {
                                'value': param_value,
                                'threshold': threshold['max'],
                                'unit': param.get('unit')
                            }
                        },
                        'severity': threshold['severity']
                    })
                
                # Check min threshold
                if 'min' in threshold and param_value < threshold['min']:
                    anomalies.append({
                        'vin': vin,
                        'timestamp': telemetry.get('timestamp'),
                        'subsystem': get_subsystem(param_name),
                        'anomaly_type': f'{param_name}_low',
                        'detection_method': 'statistical_threshold',
                        'parameters': {
                            param_name: {
                                'value': param_value,
                                'threshold': threshold['min'],
                                'unit': param.get('unit')
                            }
                        },
                        'severity': threshold['severity']
                    })
    
    return anomalies


def detect_zscore_anomalies(vin: str, data: Dict[str, Any], telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Detect anomalies using z-score analysis
    
    Args:
        vin: Vehicle identification number
        data: Telemetry data
        telemetry: Full telemetry message
        
    Returns:
        List of detected anomalies
    """
    anomalies = []
    
    # Parameters to monitor with z-score
    zscore_params = ['brake_pressure', 'pad_wear']
    
    if 'parameters' in data:
        for param in data['parameters']:
            param_name = param.get('name')
            param_value = param.get('value')
            
            if param_name in zscore_params:
                # Get historical statistics
                stats = get_historical_stats(vin, param_name, days=7)
                
                if stats and stats['count'] >= 10:  # Need minimum data points
                    # Calculate z-score
                    mean = stats['mean']
                    std_dev = stats['std_dev']
                    
                    if std_dev > 0:
                        z_score = abs((param_value - mean) / std_dev)
                        
                        # Anomaly if z-score > 3
                        if z_score > 3:
                            anomalies.append({
                                'vin': vin,
                                'timestamp': telemetry.get('timestamp'),
                                'subsystem': get_subsystem(param_name),
                                'anomaly_type': f'{param_name}_deviation',
                                'detection_method': 'zscore',
                                'parameters': {
                                    param_name: {
                                        'value': param_value,
                                        'mean': mean,
                                        'std_dev': std_dev,
                                        'z_score': z_score,
                                        'unit': param.get('unit')
                                    }
                                },
                                'severity': 'high' if z_score > 4 else 'medium'
                            })
                
                # Update statistics
                update_historical_stats(vin, param_name, param_value)
    
    return anomalies


def get_subsystem(param_name: str) -> str:
    """Get subsystem from parameter name"""
    subsystem_map = {
        'coolant_temp': 'engine',
        'engine_rpm': 'engine',
        'oil_pressure': 'engine',
        'battery_voltage': 'battery',
        'brake_pressure': 'brake',
        'pad_wear': 'brake'
    }
    return subsystem_map.get(param_name, 'unknown')


def calculate_severity_score(anomaly: Dict[str, Any]) -> int:
    """
    Calculate severity score (0-100)
    
    Args:
        anomaly: Anomaly dictionary
        
    Returns:
        Severity score
    """
    base_scores = {
        'critical': 95,
        'high': 75,
        'medium': 50,
        'warning': 30,
        'low': 15
    }
    
    severity = anomaly.get('severity', 'low')
    score = base_scores.get(severity, 50)
    
    # Adjust based on detection method
    if anomaly.get('detection_method') == 'zscore':
        params = anomaly.get('parameters', {})
        for param_data in params.values():
            if 'z_score' in param_data:
                z_score = param_data['z_score']
                # Increase score for higher z-scores
                score = min(100, score + int((z_score - 3) * 5))
    
    return score


def get_historical_stats(vin: str, param_name: str, days: int = 7) -> Optional[Dict[str, float]]:
    """Get historical statistics from DynamoDB"""
    try:
        table = dynamodb.Table(STATS_TABLE)
        response = table.get_item(
            Key={
                'vin': vin,
                'parameter': param_name
            }
        )
        
        if 'Item' in response:
            return {
                'mean': float(response['Item'].get('mean', 0)),
                'std_dev': float(response['Item'].get('std_dev', 0)),
                'count': int(response['Item'].get('count', 0))
            }
        
        return None
        
    except Exception as e:
        logger.warning(f"Error getting historical stats: {e}")
        return None


def update_historical_stats(vin: str, param_name: str, value: float) -> None:
    """Update historical statistics in DynamoDB"""
    try:
        table = dynamodb.Table(STATS_TABLE)
        
        # Get current stats
        response = table.get_item(
            Key={
                'vin': vin,
                'parameter': param_name
            }
        )
        
        if 'Item' in response:
            # Update existing stats (running average)
            item = response['Item']
            count = int(item.get('count', 0))
            mean = float(item.get('mean', 0))
            m2 = float(item.get('m2', 0))  # For Welford's algorithm
            
            count += 1
            delta = value - mean
            mean += delta / count
            delta2 = value - mean
            m2 += delta * delta2
            std_dev = (m2 / count) ** 0.5 if count > 1 else 0
            
            table.put_item(
                Item={
                    'vin': vin,
                    'parameter': param_name,
                    'mean': mean,
                    'std_dev': std_dev,
                    'm2': m2,
                    'count': count,
                    'last_updated': datetime.utcnow().isoformat()
                }
            )
        else:
            # Create new stats
            table.put_item(
                Item={
                    'vin': vin,
                    'parameter': param_name,
                    'mean': value,
                    'std_dev': 0.0,
                    'm2': 0.0,
                    'count': 1,
                    'last_updated': datetime.utcnow().isoformat()
                }
            )
            
    except Exception as e:
        logger.warning(f"Error updating historical stats: {e}")


def publish_alert(anomaly: Dict[str, Any]) -> None:
    """
    Publish critical anomaly alert to SNS
    
    Args:
        anomaly: Anomaly dictionary
    """
    try:
        # Check for duplicate alerts (15-minute suppression)
        if is_duplicate_alert(anomaly):
            logger.info("Suppressing duplicate alert")
            return
        
        # Format alert message
        message = format_alert_message(anomaly)
        
        # Publish to SNS
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"Critical Vehicle Anomaly - {anomaly['vin']}",
            Message=message
        )
        
        logger.info(f"Published alert for {anomaly['vin']}")
        
        # Record alert
        record_alert(anomaly)
        
    except Exception as e:
        logger.error(f"Error publishing alert: {e}")


def is_duplicate_alert(anomaly: Dict[str, Any]) -> bool:
    """Check if this is a duplicate alert within suppression window"""
    # Simplified - in production, check DynamoDB for recent alerts
    return False


def format_alert_message(anomaly: Dict[str, Any]) -> str:
    """Format anomaly as alert message"""
    params = anomaly.get('parameters', {})
    param_details = []
    
    for param_name, param_data in params.items():
        if 'threshold' in param_data:
            param_details.append(
                f"{param_name}: {param_data['value']} {param_data['unit']} "
                f"(threshold: {param_data['threshold']})"
            )
        elif 'z_score' in param_data:
            param_details.append(
                f"{param_name}: {param_data['value']} {param_data['unit']} "
                f"(z-score: {param_data['z_score']:.2f})"
            )
    
    message = f"""
CRITICAL VEHICLE ANOMALY DETECTED

Vehicle: {anomaly['vin']}
Subsystem: {anomaly['subsystem']}
Anomaly Type: {anomaly['anomaly_type']}
Severity Score: {anomaly['severity_score']}/100
Detection Method: {anomaly['detection_method']}
Timestamp: {anomaly['timestamp']}

Parameters:
{chr(10).join(param_details)}

Immediate action may be required.
"""
    
    return message


def record_alert(anomaly: Dict[str, Any]) -> None:
    """Record alert in DynamoDB for suppression tracking"""
    # Implementation would store alert with timestamp
    pass
