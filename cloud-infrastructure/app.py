#!/usr/bin/env python3
"""
ECU Diagnostics System - AWS CDK Application Entry Point
"""
import os
import aws_cdk as cdk
from aws_cdk import Environment

# Import stacks (will be created in subsequent tasks)
# from stacks.iot_stack import IoTStack
# from stacks.storage_stack import StorageStack
# from stacks.compute_stack import ComputeStack
# from stacks.api_stack import ApiStack

app = cdk.App()

# Get environment configuration
env_name = app.node.try_get_context("env") or "dev"
account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

env = Environment(account=account, region=region)

# Stack instantiation will be added as we implement each component
# Example:
# iot_stack = IoTStack(app, f"EcuDiagnostics-IoT-{env_name}", env=env)
# storage_stack = StorageStack(app, f"EcuDiagnostics-Storage-{env_name}", env=env)

app.synth()
