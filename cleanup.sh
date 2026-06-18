#!/bin/bash
# =============================================================================
# cleanup.sh — Tear down all AWS resources created by this project
# =============================================================================
set -euo pipefail

source .env

echo "============================================"
echo "  WC Live Commentary — Resource Cleanup"
echo "============================================"
echo ""
echo "⚠️  This will DELETE all project resources!"
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

echo ""

# 1. Delete Lambda functions
echo "🗑  Deleting Lambda functions..."
aws lambda delete-function --function-name wc-commentary 2>/dev/null || true
aws lambda delete-function --function-name wc-ws-connect 2>/dev/null || true
echo "✓ Lambda functions deleted"

# 2. Delete Kinesis stream
echo "🗑  Deleting Kinesis stream..."
aws kinesis delete-stream --stream-name "$KINESIS_STREAM_NAME" 2>/dev/null || true
echo "✓ Kinesis stream deleted"

# 3. Delete DynamoDB tables
echo "🗑  Deleting DynamoDB tables..."
aws dynamodb delete-table --table-name "$DYNAMO_TABLE_NAME" 2>/dev/null || true
aws dynamodb delete-table --table-name wc-ws-connections 2>/dev/null || true
echo "✓ DynamoDB tables deleted"

# 4. Delete S3 bucket (must empty first)
echo "🗑  Emptying and deleting S3 bucket..."
aws s3 rm "s3://${S3_BUCKET_NAME}" --recursive 2>/dev/null || true
aws s3api delete-bucket --bucket "$S3_BUCKET_NAME" 2>/dev/null || true
echo "✓ S3 bucket deleted"

# 5. Delete WebSocket API
echo "🗑  Deleting WebSocket API Gateway..."
API_ID=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='wc-live-ws'].ApiId" --output text 2>/dev/null || true)
if [ -n "$API_ID" ]; then
  aws apigatewayv2 delete-api --api-id "$API_ID" 2>/dev/null || true
fi
echo "✓ API Gateway deleted"

# 6. Delete IAM role (detach policies first)
echo "🗑  Deleting IAM role..."
POLICIES=(
  "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
  "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  "arn:aws:iam::aws:policy/AmazonKinesisReadOnlyAccess"
  "arn:aws:iam::aws:policy/service-role/AWSLambdaKinesisExecutionRole"
  "arn:aws:iam::aws:policy/AmazonAPIGatewayInvokeFullAccess"
  "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)
for policy in "${POLICIES[@]}"; do
  aws iam detach-role-policy --role-name wc-lambda-role \
    --policy-arn "$policy" 2>/dev/null || true
done
aws iam delete-role --role-name wc-lambda-role 2>/dev/null || true
echo "✓ IAM role deleted"

echo ""
echo "============================================"
echo "  ✅ All resources cleaned up!"
echo "============================================"
