#!/usr/bin/env python3
"""
ECU Diagnostics System - AWS CDK Application Entry Point
"""
import os
import aws_cdk as cdk
from aws_cdk import Environment

# Import stacks
from stacks.iot_stack import IoTStack
from stacks.storage_stack import StorageStack
from stacks.redshift_stack import RedshiftStack

app = cdk.App()

# Get environment configuration
env_name = app.node.try_get_context("env") or "dev"
account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

env = Environment(account=account, region=region)

# Create stacks
iot_stack = IoTStack(
    app, 
    f"EcuDiagnostics-IoT-{env_name}", 
    env=env,
    description="IoT Core resources for ECU diagnostics"
)

storage_stack = StorageStack(
    app, 
    f"EcuDiagnostics-Storage-{env_name}", 
    env=env,
    description="S3 buckets and storage for telemetry data"
)

redshift_stack = RedshiftStack(
    app, 
    f"EcuDiagnostics-Redshift-{env_name}", 
    env=env,
    description="Redshift data warehouse for analytics"
)

# Add dependencies
storage_stack.add_dependency(iot_stack)
redshift_stack.add_dependency(storage_stack)

app.synth()
