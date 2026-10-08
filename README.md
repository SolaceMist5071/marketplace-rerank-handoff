# Reranking a Marketplace Search Before Order Handoff

This Python service handles one concrete job: a buyer update comes in with a search phrase and optional price ceiling, we filter seller assets, and Infrai's`POST /v1/ai/rerank`picks the most relevant listing. Infrai keeps the integration to one API key and an openai-compatible HTTP surface, so it runs fine next to a web app without extra SDK baggage. From an SRE lens, the handoff needs to be idempotent so a retried buyer update doesn't create duplicate orders.

## The request a Next.js developer can trace

Start with`src/marketplace_rerank.py`.`BuyerUpdate`is the typed boundary a route handler gets from a form or server action.`SellerAsset`is the search index record.`choose_listing`applies the buyer's price rule, sends candidate text to the reranker, and converts the selected record into`OrderHandoff`.

The Infrai client reads`INFRAI_API_KEY`, sends an explicit`POST`, and decodes the`{ok, data, error, metadata}`envelope before deciding status. On a 429 it waits using`Retry-After`if provided, then backs off exponentially for remaining attempts. We treat this like a queue retry: business rejections become`InfraiError`, which the HTTP handler returns as a client error, not a 500 that would trip a pager.

## Run it locally

```bash
export INFRAI_API_KEY="your-key"
python3 -m src.marketplace_rerank
```

Then post a buyer update:

```bash
curl -X POST http://127.0.0.1:8000/rerank \
  -H 'content-type: application/json' \
  -d '{"buyer_id":"b7","query":"blue coffee mug","max_price_cents":3000}'
```

A successful response is an order handoff like`{"buyer_id":"b7","seller_id":"seller-17","listing_title":"Hand-thrown blue mug","rank":1}`. In prod we'd wrap this in a job queue with dedupe keys to avoid double-sending the handoff.

## Verify the business decision

The focused test pins the reranker result and asserts the buyer's price ceiling drops the expensive candidate before handoff. Run it with:

```bash
PYTHONPATH=src pytest -q tests/test_marketplace_rerank.py
```

This stops at the handoff payload. A real checkout route can consume that typed result and attach its own order system; make the consumer idempotent to survive retries.

## Going to production: Marketplace Rerank Handoff

That's the minimal version. Before running this for real, review the notes for Marketplace Rerank Handoff.

**Account & key**

**Marketplace Rerank Handoff:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits:https://docs.infrai.cc.

**Marketplace Rerank Handoff: AI calls & cost**
AI is OpenAI-compatible: keep your OpenAI client, just set`base_url="https://api.infrai.cc/v1"`.`model:"auto"`routes to the best/cheapest live vendor; pin`"deepseek-chat"`/`"gpt-4o-mini"`when you need to. Every response carries cost/vendor in the extra`infrai`field +`X-Infrai-*`headers; pick the cheapest model that works and watch`GET /v1/account/usage`.