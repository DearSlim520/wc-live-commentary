"""
Infrastructure Setup: Create all AWS resources in one shot.

Usage:
    python infra/setup.py

Creates:
- Kinesis Data Stream (1 shard)
- DynamoDB tables (commentary + WebSocket connections)
- S3 bucket with static website hosting
- IAM role for Lambda
"""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

region = os.environ["AWS_REGION"]
stream = os.environ["KINESIS_STREAM_NAME"]
table = os.environ["DYNAMO_TABLE_NAME"]
bucket = os.environ["S3_BUCKET_NAME"]

kinesis = boto3.client("kinesis", region_name=region)
dynamo = boto3.client("dynamodb", region_name=region)
s3 = boto3.client("s3", region_name=region)
iam = boto3.client("iam", region_name=region)

print("=" * 60)
print("  World Cup 2026 Live Commentary — AWS Resource Setup")
print("=" * 60)
print()

# 1. Kinesis stream
try:
    kinesis.create_stream(StreamName=stream, ShardCount=1)
    print(f"✓ Kinesis stream '{stream}' created")
except kinesis.exceptions.ResourceInUseException:
    print(f"✓ Kinesis stream '{stream}' already exists, skipping")

# 2. DynamoDB commentary table
#    PK: match_id (S)   SK: event_ts (S, ISO8601 — sorts chronologically)
try:
    dynamo.create_table(
        TableName=table,
        KeySchema=[
            {"AttributeName": "match_id", "KeyType": "HASH"},
            {"AttributeName": "event_ts", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "match_id", "AttributeType": "S"},
            {"AttributeName": "event_ts", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"✓ DynamoDB table '{table}' created")
except dynamo.exceptions.ResourceInUseException:
    print(f"✓ DynamoDB table '{table}' already exists, skipping")

# 3. DynamoDB WebSocket connections table
try:
    dynamo.create_table(
        TableName="wc-ws-connections",
        KeySchema=[
            {"AttributeName": "connection_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "connection_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    print("✓ DynamoDB table 'wc-ws-connections' created")
except dynamo.exceptions.ResourceInUseException:
    print("✓ DynamoDB table 'wc-ws-connections' already exists, skipping")

# 4. S3 bucket
try:
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket)
    else:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
    print(f"✓ S3 bucket '{bucket}' created")
except s3.exceptions.BucketAlreadyOwnedByYou:
    print(f"✓ S3 bucket '{bucket}' already exists")
except Exception as e:
    if "BucketAlreadyExists" in str(e):
        print(f"⚠ S3 bucket name '{bucket}' is taken globally. Choose a unique name.")
    else:
        raise

# Disable Block Public Access so we can set a public policy
try:
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": False,
            "IgnorePublicAcls": False,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    )
    print(f"✓ S3 Block Public Access disabled for '{bucket}'")
except Exception as e:
    print(f"⚠ Could not disable Block Public Access: {e}")

# Enable static website hosting
try:
    s3.put_bucket_website(
        Bucket=bucket,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
        },
    )
    # Public read access for static site
    s3.put_bucket_policy(
        Bucket=bucket,
        Policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "s3:GetObject",
                        "Resource": f"arn:aws:s3:::{bucket}/*",
                    }
                ],
            }
        ),
    )
    print(f"✓ S3 static website hosting + public policy configured")
except Exception as e:
    print(f"⚠ S3 website/policy config error: {e}")

# 5. IAM role for Lambda
trust = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}

POLICIES = [
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonKinesisReadOnlyAccess",
    "arn:aws:iam::aws:policy/service-role/AWSLambdaKinesisExecutionRole",
    "arn:aws:iam::aws:policy/AmazonAPIGatewayInvokeFullAccess",
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
]

try:
    role = iam.create_role(
        RoleName="wc-lambda-role",
        AssumeRolePolicyDocument=json.dumps(trust),
        Description="Lambda execution role for WC Live Commentary pipeline",
    )
    for policy_arn in POLICIES:
        iam.attach_role_policy(RoleName="wc-lambda-role", PolicyArn=policy_arn)
    print(f"✓ IAM role 'wc-lambda-role' created: {role['Role']['Arn']}")
except iam.exceptions.EntityAlreadyExistsException:
    print("✓ IAM role 'wc-lambda-role' already exists, skipping")

print()
print("=" * 60)
print("  All resources created!")
print("  Wait ~30s for Kinesis stream to become ACTIVE.")
print("=" * 60)
