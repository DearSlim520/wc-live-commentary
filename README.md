# ⚽ World Cup 2026 — Real-time Text Commentary Pipeline

A real-time AWS streaming pipeline that pulls live World Cup match events from football-data.org, generates Chinese AI commentary via Claude API, and pushes it to a browser via WebSocket.

## Architecture

```
football-data.org API
        │
        ▼
  Python Poller (local)
        │  JSON event
        ▼
Kinesis Data Streams (1 shard)
        │
        ▼
  Lambda Consumer
  ├── parse event
  ├── call Claude API → 中文解说词
  ├── write → DynamoDB  (wc-commentary table)
  ├── write → S3        (raw event archive)
  └── push → API Gateway WebSocket connections
        │
        ▼
  S3 Static Site  (index.html — WebSocket client)
```

## Tech Stack

| Component | Service |
|-----------|---------|
| Event Source | football-data.org REST API |
| Ingestion | Python poller → Kinesis Data Streams |
| Processing | AWS Lambda (Python 3.12) |
| AI Commentary | Anthropic Claude API |
| Storage | DynamoDB (on-demand) + S3 |
| Real-time Push | API Gateway WebSocket |
| Frontend | S3 static website |

## Cost

< **$2 per match** on fully managed AWS infrastructure:
- Kinesis: 1 shard-hour ~$0.015
- Lambda: within free tier
- DynamoDB: on-demand, pennies per match
- S3: negligible

## Quick Start

### Prerequisites

```bash
python3 --version      # 3.10+
aws --version          # AWS CLI v2, configured
pip install -r requirements.txt
```

- Get a free API key at https://www.football-data.org/client/register
- Get an Anthropic API key at https://console.anthropic.com

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and preferred AWS region
```

### 2. Create AWS resources

```bash
python infra/setup.py
# Wait ~30s for Kinesis stream to become ACTIVE
```

### 3. Deploy Lambda & API Gateway

```bash
chmod +x deploy.sh
./deploy.sh
```

### 4. Start the poller

```bash
python poller.py
```

### 5. Open the live site

The URL is printed at the end of `deploy.sh`. Open it in your browser to see real-time commentary appear as match events flow in.

## Project Structure

```
wc-live-commentary/
├── .env.example          # Environment template
├── .gitignore
├── README.md
├── requirements.txt      # Python dependencies
├── poller.py             # Polls football-data.org → Kinesis
├── lambda_handler.py     # Lambda: Kinesis → Claude → DynamoDB + WebSocket
├── ws_handler.py         # Lambda: WebSocket $connect/$disconnect
├── deploy.sh             # Deploy Lambda + API GW + upload frontend
├── cleanup.sh            # Tear down all AWS resources
├── infra/
│   └── setup.py          # Create AWS resources (Kinesis, DynamoDB, S3, IAM)
└── frontend/
    └── index.html        # WebSocket browser client
```

## Key Design Decisions

- **Event-driven streaming**: Kinesis decouples the poller from processing — neither blocks the other
- **Exactly-once semantics**: Kinesis sequence numbers + DynamoDB conditional writes prevent duplicate commentary on retry
- **AI integration**: Claude API called synchronously in Lambda; 10s timeout with graceful fallback to rule-based commentary so the pipeline never stalls
- **Schema design**: DynamoDB `PK=match_id` `SK=event_ts` (ISO8601) — SK sorts chronologically for free, enabling efficient `query(match_id, begins_with("2026-06"))` to replay a full match
- **Cost efficiency**: All managed services scale to 0 between matches

## Cleanup

```bash
chmod +x cleanup.sh
./cleanup.sh
```

## Resume Bullet

> Built a real-time World Cup text commentary pipeline on AWS (Kinesis → Lambda → DynamoDB → WebSocket) integrating Claude API for AI-generated Chinese play-by-play; delivered sub-60s event-to-browser latency at < $2/match on fully managed infrastructure.

---

## License

MIT
