"""
Lambda Consumer: Kinesis → Claude API → DynamoDB + S3 + WebSocket

Triggered by Kinesis records. For each match event:
1. Archives raw event to S3
2. Generates Chinese AI commentary via Claude API
3. Writes commentary to DynamoDB
4. Pushes to WebSocket clients via API Gateway Management API
"""

import boto3
import json
import os
import base64
from datetime import datetime, timezone
from urllib.request import urlopen, Request

DYNAMO_TABLE = os.environ["DYNAMO_TABLE_NAME"]
S3_BUCKET = os.environ["S3_BUCKET_NAME"]
WS_ENDPOINT = os.environ.get("WS_ENDPOINT", "")  # set after API GW created
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

dynamo = boto3.resource("dynamodb").Table(DYNAMO_TABLE)
s3 = boto3.client("s3")

EVENT_TYPE_ZH = {
    "GOAL": "⚽ 进球",
    "YELLOW_CARD": "🟨 黄牌",
    "RED_CARD": "🟥 红牌",
    "SUBSTITUTION": "🔄 换人",
    "HALF_TIME": "🔔 半场",
    "FULL_TIME": "🏁 终场",
    "STATUS": "📡 直播中",
}


def generate_commentary(event: dict) -> str:
    """Call Claude API to generate a short Chinese commentary sentence."""
    event_type = EVENT_TYPE_ZH.get(event["type"], event["type"])
    prompt = (
        f"你是一名专业的中文足球解说员。请用一句话（20-40字）为以下比赛事件生成生动的解说词。\n"
        f"只输出解说词本身，不要加任何前缀或标签。\n\n"
        f"比赛：{event.get('home', '?')} vs {event.get('away', '?')}\n"
        f"事件类型：{event_type}\n"
        f"当前比分：{event.get('score', '?')}\n"
        f"比赛时间：第{event.get('minute', '?')}分钟\n"
        f"详情：{event.get('detail', '')}"
    )
    payload = json.dumps(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": 100,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
    return body["content"][0]["text"].strip()


def push_to_websocket(item: dict):
    """Broadcast commentary to all connected WebSocket clients."""
    if not WS_ENDPOINT:
        return
    apigw = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=WS_ENDPOINT,
    )
    # Fetch active connection IDs from DynamoDB connections table
    conn_table = boto3.resource("dynamodb").Table("wc-ws-connections")
    conns = conn_table.scan(ProjectionExpression="connection_id")["Items"]
    msg = json.dumps(item, ensure_ascii=False).encode()
    for c in conns:
        try:
            apigw.post_to_connection(ConnectionId=c["connection_id"], Data=msg)
        except apigw.exceptions.GoneException:
            conn_table.delete_item(Key={"connection_id": c["connection_id"]})
        except Exception as e:
            print(f"WebSocket push error for {c['connection_id']}: {e}")


def lambda_handler(event, context):
    for record in event["Records"]:
        raw = base64.b64decode(record["kinesis"]["data"]).decode()
        ev = json.loads(raw)
        ts = ev.get("event_ts", datetime.now(timezone.utc).isoformat())

        # 1. Archive raw event to S3
        key = f"raw/{ev.get('match_id', 'unknown')}/{ts}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=raw,
            ContentType="application/json",
        )

        # 2. Generate AI commentary
        try:
            commentary = generate_commentary(ev)
        except Exception as e:
            commentary = (
                f"{EVENT_TYPE_ZH.get(ev['type'], ev['type'])} {ev.get('detail', '')}"
            )
            print(f"Claude API error (fallback used): {e}")

        # 3. Write to DynamoDB
        item = {
            "match_id": str(ev.get("match_id", "unknown")),
            "event_ts": ts,
            "type": ev.get("type"),
            "score": ev.get("score", "0:0"),
            "minute": str(ev.get("minute", "?")),
            "home": ev.get("home", ""),
            "away": ev.get("away", ""),
            "commentary": commentary,
            "raw_detail": ev.get("detail", ""),
        }
        dynamo.put_item(Item=item)

        # 4. Push to WebSocket clients
        push_to_websocket(item)

        print(f"✓ {ev['type']} | {commentary[:40]}...")

    return {"statusCode": 200}
