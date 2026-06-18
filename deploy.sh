#!/bin/bash
# =============================================================================
# deploy.sh — Deploy Lambda functions and wire up Kinesis + WebSocket API
# =============================================================================
set -euo pipefail

# Load environment variables
source .env

echo "============================================"
echo "  WC Live Commentary — Lambda Deployment"
echo "============================================"
echo ""

# --- 1. Package Lambda functions ---
echo "📦 Packaging Lambda functions..."
zip -j lambda.zip lambda_handler.py
zip -j ws_lambda.zip ws_handler.py

# --- 2. Get IAM Role ARN ---
ROLE_ARN=$(aws iam get-role --role-name wc-lambda-role \
  --query 'Role.Arn' --output text)
echo "✓ Role ARN: $ROLE_ARN"

# Wait for role propagation
echo "  Waiting 10s for IAM role propagation..."
sleep 10

# --- 3. Deploy main commentary Lambda ---
echo ""
echo "🚀 Deploying wc-commentary Lambda..."
aws lambda create-function \
  --function-name wc-commentary \
  --runtime python3.12 \
  --role "$ROLE_ARN" \
  --handler lambda_handler.lambda_handler \
  --zip-file fileb://lambda.zip \
  --timeout 30 \
  --memory-size 256 \
  --environment "Variables={DYNAMO_TABLE_NAME=${DYNAMO_TABLE_NAME},S3_BUCKET_NAME=${S3_BUCKET_NAME},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},CLAUDE_MODEL=${CLAUDE_MODEL}}" \
  --no-cli-pager 2>/dev/null || \
  echo "  (function may already exist — updating code...)" && \
  aws lambda update-function-code \
    --function-name wc-commentary \
    --zip-file fileb://lambda.zip \
    --no-cli-pager 2>/dev/null

echo "✓ wc-commentary Lambda deployed"

# --- 4. Deploy WebSocket handler Lambda ---
echo ""
echo "🚀 Deploying wc-ws-connect Lambda..."
aws lambda create-function \
  --function-name wc-ws-connect \
  --runtime python3.12 \
  --role "$ROLE_ARN" \
  --handler ws_handler.lambda_handler \
  --zip-file fileb://ws_lambda.zip \
  --timeout 10 \
  --environment "Variables={CONNECTIONS_TABLE=wc-ws-connections}" \
  --no-cli-pager 2>/dev/null || \
  echo "  (function may already exist — updating code...)" && \
  aws lambda update-function-code \
    --function-name wc-ws-connect \
    --zip-file fileb://ws_lambda.zip \
    --no-cli-pager 2>/dev/null

echo "✓ wc-ws-connect Lambda deployed"

# --- 5. Add Kinesis trigger to commentary Lambda ---
echo ""
echo "🔗 Adding Kinesis event source mapping..."
STREAM_ARN=$(aws kinesis describe-stream \
  --stream-name "$KINESIS_STREAM_NAME" \
  --query 'StreamDescription.StreamARN' --output text)

aws lambda create-event-source-mapping \
  --function-name wc-commentary \
  --event-source-arn "$STREAM_ARN" \
  --starting-position LATEST \
  --batch-size 1 \
  --no-cli-pager 2>/dev/null || \
  echo "  (event source mapping may already exist)"

echo "✓ Kinesis → Lambda trigger configured"

# --- 6. Create WebSocket API Gateway ---
echo ""
echo "🌐 Creating WebSocket API Gateway..."
API_ID=$(aws apigatewayv2 create-api \
  --name wc-live-ws \
  --protocol-type WEBSOCKET \
  --route-selection-expression '$request.body.action' \
  --query 'ApiId' --output text 2>/dev/null || true)

if [ -z "$API_ID" ]; then
  API_ID=$(aws apigatewayv2 get-apis \
    --query "Items[?Name=='wc-live-ws'].ApiId" --output text)
fi

echo "✓ WebSocket API ID: $API_ID"

WS_URL="wss://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"
echo "✓ WebSocket URL: $WS_URL"

# --- 7. Update commentary Lambda with WS endpoint ---
WS_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"
aws lambda update-function-configuration \
  --function-name wc-commentary \
  --environment "Variables={DYNAMO_TABLE_NAME=${DYNAMO_TABLE_NAME},S3_BUCKET_NAME=${S3_BUCKET_NAME},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},CLAUDE_MODEL=${CLAUDE_MODEL},WS_ENDPOINT=${WS_ENDPOINT}}" \
  --no-cli-pager 2>/dev/null

echo "✓ Updated wc-commentary with WS_ENDPOINT"

# --- 8. Upload frontend ---
echo ""
echo "📄 Uploading frontend to S3..."
# Replace placeholder WebSocket URL in index.html
sed "s|wss://YOUR_API_ID.execute-api.us-west-2.amazonaws.com/prod|${WS_URL}|g" \
  frontend/index.html > /tmp/index_deploy.html

aws s3 cp /tmp/index_deploy.html "s3://${S3_BUCKET_NAME}/index.html" \
  --content-type "text/html" --no-cli-pager

SITE_URL="http://${S3_BUCKET_NAME}.s3-website-${AWS_REGION}.amazonaws.com"
echo "✓ Frontend uploaded"

# --- Done ---
echo ""
echo "============================================"
echo "  ✅ Deployment Complete!"
echo "============================================"
echo ""
echo "  WebSocket URL: $WS_URL"
echo "  Live Site:     $SITE_URL"
echo ""
echo "  Next steps:"
echo "    1. python poller.py          (start polling)"
echo "    2. Open $SITE_URL in browser"
echo ""

# Cleanup
rm -f lambda.zip ws_lambda.zip /tmp/index_deploy.html
