"""
Poller: football-data.org → Kinesis Data Streams

Polls the football-data.org API for live World Cup 2026 matches every 60s,
detects state changes (goals, status), and emits events to Kinesis.

Usage:
    python poller.py
"""

import boto3
import requests
import json
import time
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["FOOTBALL_API_KEY"]
STREAM = os.environ["KINESIS_STREAM_NAME"]
REGION = os.environ["AWS_REGION"]

kinesis = boto3.client("kinesis", region_name=REGION)
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}

# World Cup 2026 competition code
WC_ID = "WC"


def get_live_matches():
    """Return list of matches currently LIVE or IN_PLAY."""
    r = requests.get(
        f"{BASE_URL}/competitions/{WC_ID}/matches",
        headers=HEADERS,
        params={"status": "LIVE,IN_PLAY"},
    )
    r.raise_for_status()
    return r.json().get("matches", [])


def get_match_detail(match_id):
    """Fetch full detail for a single match."""
    r = requests.get(f"{BASE_URL}/matches/{match_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def emit_event(event: dict):
    """Put a single event onto Kinesis."""
    kinesis.put_record(
        StreamName=STREAM,
        Data=json.dumps(event, ensure_ascii=False),
        PartitionKey=str(event.get("match_id", "default")),
    )
    print(f"  → emitted: {event['type']} | {event.get('detail', '')}")


# Track seen goals to avoid duplicate emits
_seen_goals = {}


def diff_and_emit(match):
    """Detect state changes vs last poll and emit delta events."""
    mid = str(match["id"])
    score = match["score"]["fullTime"]
    ht = match["homeTeam"]["name"]
    at = match["awayTeam"]["name"]
    ts = datetime.now(timezone.utc).isoformat()

    key = f"{score['home']}-{score['away']}"
    if _seen_goals.get(mid) != key:
        # Score changed → goal event
        emit_event(
            {
                "type": "GOAL",
                "match_id": mid,
                "home": ht,
                "away": at,
                "score": f"{score['home']}:{score['away']}",
                "minute": match.get("minute", "?"),
                "detail": f"{ht} {score['home']} - {score['away']} {at}",
                "event_ts": ts,
            }
        )
        _seen_goals[mid] = key
    else:
        # Heartbeat — match is ongoing
        emit_event(
            {
                "type": "STATUS",
                "match_id": mid,
                "home": ht,
                "away": at,
                "score": f"{score['home']}:{score['away']}",
                "status": match["status"],
                "minute": match.get("minute", "?"),
                "detail": f"第 {match.get('minute', '?')} 分钟",
                "event_ts": ts,
            }
        )


def main():
    print("🟢 Poller started — polling every 60s (free tier rate limit)")
    print(f"   Stream: {STREAM} | Region: {REGION}")
    print(f"   Competition: World Cup 2026 ({WC_ID})")
    print()

    while True:
        try:
            matches = get_live_matches()
            if not matches:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] No live matches right now"
                )
            for m in matches:
                diff_and_emit(m)
        except requests.HTTPError as e:
            print(f"API error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
