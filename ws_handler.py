"""
WebSocket Connection Handler Lambda

Handles $connect and $disconnect routes for API Gateway WebSocket API.
Stores/removes connection IDs in DynamoDB (wc-ws-connections table).
"""

import boto3
import os

CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "wc-ws-connections")
dynamo = boto3.resource("dynamodb").Table(CONNECTIONS_TABLE)


def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    route_key = event["requestContext"]["routeKey"]

    if route_key == "$connect":
        # Store new connection
        dynamo.put_item(Item={"connection_id": connection_id})
        print(f"✓ Connected: {connection_id}")
        return {"statusCode": 200, "body": "Connected"}

    elif route_key == "$disconnect":
        # Remove connection
        dynamo.delete_item(Key={"connection_id": connection_id})
        print(f"✓ Disconnected: {connection_id}")
        return {"statusCode": 200, "body": "Disconnected"}

    return {"statusCode": 400, "body": "Unknown route"}
