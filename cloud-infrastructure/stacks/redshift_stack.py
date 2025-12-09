"""
Redshift Data Warehouse Stack

Creates Redshift cluster and database schema for analytics.
"""
from aws_cdk import (
    Stack,
    aws_redshift as redshift,
    aws_ec2 as ec2,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct


class RedshiftStack(Stack):
    """Redshift data warehouse stack"""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create VPC for Redshift
        self.vpc = ec2.Vpc(
            self, "RedshiftVPC",
            max_azs=2,
            nat_gateways=1
        )
        
        # Create security group
        self.security_group = ec2.SecurityGroup(
            self, "RedshiftSecurityGroup",
            vpc=self.vpc,
            description="Security group for Redshift cluster",
            allow_all_outbound=True
        )
        
        # Allow inbound from VPC
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5439),
            description="Allow Redshift access from VPC"
        )
        
        # Create master user secret
        self.master_secret = secretsmanager.Secret(
            self, "RedshiftMasterSecret",
            description="Redshift master user credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "admin"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=32
            )
        )
        
        # Create subnet group
        self.subnet_group = redshift.CfnClusterSubnetGroup(
            self, "RedshiftSubnetGroup",
            description="Subnet group for Redshift cluster",
            subnet_ids=[subnet.subnet_id for subnet in self.vpc.private_subnets]
        )
        
        # Create Redshift cluster
        self.cluster = redshift.CfnCluster(
            self, "RedshiftCluster",
            cluster_type="multi-node",
            node_type="dc2.large",
            number_of_nodes=2,
            db_name="ecudiagnostics",
            master_username=self.master_secret.secret_value_from_json("username").unsafe_unwrap(),
            master_user_password=self.master_secret.secret_value_from_json("password").unsafe_unwrap(),
            cluster_subnet_group_name=self.subnet_group.ref,
            vpc_security_group_ids=[self.security_group.security_group_id],
            publicly_accessible=False,
            encrypted=True,
            automated_snapshot_retention_period=7
        )
        
        # Create IAM role for Redshift to access S3
        self.redshift_role = iam.Role(
            self, "RedshiftS3Role",
            assumed_by=iam.ServicePrincipal("redshift.amazonaws.com"),
            description="Role for Redshift to access S3"
        )
        
        # Grant S3 read access
        self.redshift_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=["arn:aws:s3:::ecu-diagnostics-*/*"]
            )
        )
        
        # Outputs
        CfnOutput(
            self, "RedshiftClusterEndpoint",
            value=self.cluster.attr_endpoint_address,
            description="Redshift cluster endpoint"
        )
        
        CfnOutput(
            self, "RedshiftClusterPort",
            value=self.cluster.attr_endpoint_port,
            description="Redshift cluster port"
        )
        
        CfnOutput(
            self, "RedshiftMasterSecretArn",
            value=self.master_secret.secret_arn,
            description="ARN of Redshift master credentials secret"
        )
        
        CfnOutput(
            self, "RedshiftRoleArn",
            value=self.redshift_role.role_arn,
            description="ARN of Redshift IAM role"
        )
