"""
Storage Stack

Creates S3 buckets and Kinesis Firehose for telemetry storage.
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_kms as kms,
    aws_iot as iot,
    aws_iam as iam,
    aws_kinesisfirehose as firehose,
    CfnOutput
)
from constructs import Construct


class StorageStack(Stack):
    """Storage infrastructure stack"""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create KMS key for encryption
        self.kms_key = kms.Key(
            self, "TelemetryEncryptionKey",
            description="Encryption key for ECU telemetry data",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN
        )
        
        # Create S3 bucket for raw telemetry
        self.telemetry_bucket = s3.Bucket(
            self, "TelemetryBucket",
            bucket_name=f"ecu-diagnostics-telemetry-{self.account}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToGlacier",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90)
                        )
                    ]
                )
            ],
            removal_policy=RemovalPolicy.RETAIN
        )
        
        # Create S3 bucket for OTA logs
        self.ota_logs_bucket = s3.Bucket(
            self, "OTALogsBucket",
            bucket_name=f"ecu-diagnostics-ota-logs-{self.account}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldLogs",
                    expiration=Duration.days(365)
                )
            ],
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Create S3 bucket for ML models
        self.ml_models_bucket = s3.Bucket(
            self, "MLModelsBucket",
            bucket_name=f"ecu-diagnostics-ml-models-{self.account}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN
        )
        
        # Create IAM role for IoT Rules to write to S3
        self.iot_s3_role = iam.Role(
            self, "IoTS3Role",
            assumed_by=iam.ServicePrincipal("iot.amazonaws.com"),
            description="Role for IoT Rules to write to S3"
        )
        
        self.telemetry_bucket.grant_write(self.iot_s3_role)
        
        # Create IoT Rule to route telemetry to S3
        self.telemetry_rule = iot.CfnTopicRule(
            self, "TelemetryToS3Rule",
            rule_name="ECUDiagnosticsTelemetryToS3",
            topic_rule_payload=iot.CfnTopicRule.TopicRulePayloadProperty(
                sql="SELECT * FROM 'vehicle/+/telemetry'",
                description="Route all vehicle telemetry to S3",
                actions=[
                    iot.CfnTopicRule.ActionProperty(
                        s3=iot.CfnTopicRule.S3ActionProperty(
                            bucket_name=self.telemetry_bucket.bucket_name,
                            key="${topic(2)}/year=${timestamp().year}/month=${timestamp().month}/day=${timestamp().day}/${timestamp()}-${newuuid()}.json",
                            role_arn=self.iot_s3_role.role_arn
                        )
                    )
                ],
                error_action=iot.CfnTopicRule.ActionProperty(
                    cloudwatch_logs=iot.CfnTopicRule.CloudwatchLogsActionProperty(
                        log_group_name="/aws/iot/rules/errors",
                        role_arn=self.iot_s3_role.role_arn
                    )
                )
            )
        )
        
        # Outputs
        CfnOutput(
            self, "TelemetryBucketName",
            value=self.telemetry_bucket.bucket_name,
            description="S3 bucket for telemetry data"
        )
        
        CfnOutput(
            self, "OTALogsBucketName",
            value=self.ota_logs_bucket.bucket_name,
            description="S3 bucket for OTA logs"
        )
        
        CfnOutput(
            self, "MLModelsBucketName",
            value=self.ml_models_bucket.bucket_name,
            description="S3 bucket for ML models"
        )
