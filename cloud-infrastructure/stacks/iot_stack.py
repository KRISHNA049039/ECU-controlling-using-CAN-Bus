"""
AWS IoT Core Stack

Creates IoT Things, certificates, policies, and rules for vehicle connectivity.
"""
from aws_cdk import (
    Stack,
    aws_iot as iot,
    aws_iam as iam,
    CfnOutput
)
from constructs import Construct


class IoTStack(Stack):
    """AWS IoT Core infrastructure stack"""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create IoT Policy for vehicles
        self.iot_policy = iot.CfnPolicy(
            self, "VehicleIoTPolicy",
            policy_name="ECUDiagnosticsVehiclePolicy",
            policy_document={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["iot:Connect"],
                        "Resource": [f"arn:aws:iot:{self.region}:{self.account}:client/${{iot:ClientId}}"]
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["iot:Publish"],
                        "Resource": [
                            f"arn:aws:iot:{self.region}:{self.account}:topic/vehicle/${{iot:ClientId}}/telemetry",
                            f"arn:aws:iot:{self.region}:{self.account}:topic/vehicle/${{iot:ClientId}}/status",
                            f"arn:aws:iot:{self.region}:{self.account}:topic/vehicle/${{iot:ClientId}}/ota/status"
                        ]
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["iot:Subscribe"],
                        "Resource": [
                            f"arn:aws:iot:{self.region}:{self.account}:topicfilter/vehicle/${{iot:ClientId}}/commands/*"
                        ]
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["iot:Receive"],
                        "Resource": [
                            f"arn:aws:iot:{self.region}:{self.account}:topic/vehicle/${{iot:ClientId}}/commands/*"
                        ]
                    }
                ]
            }
        )
        
        # Create Thing Type for vehicles
        self.thing_type = iot.CfnThingType(
            self, "VehicleThingType",
            thing_type_name="ECUDiagnosticsVehicle",
            thing_type_properties=iot.CfnThingType.ThingTypePropertiesProperty(
                searchable_attributes=["vin", "make", "model", "year"],
                thing_type_description="Vehicle with ECU diagnostics capability"
            )
        )
        
        # Outputs
        CfnOutput(
            self, "IoTPolicyName",
            value=self.iot_policy.policy_name,
            description="IoT Policy name for vehicles"
        )
        
        CfnOutput(
            self, "ThingTypeName",
            value=self.thing_type.thing_type_name,
            description="Thing Type name for vehicles"
        )
        
        CfnOutput(
            self, "IoTEndpoint",
            value=f"https://{self.account}.iot.{self.region}.amazonaws.com",
            description="IoT Core endpoint"
        )
