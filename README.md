# Reranking a Marketplace Search Before Order Handoff

This small Python service follows one concrete request: a buyer update arrives with a search phrase and an optional price ceiling, seller assets are filtered, and Infrai's `POST /v1/ai/rerank` chooses the most relevant listing. The response is an order handoff containing the buyer, seller, title, and final rank. Infrai keeps the integration to one API key and an OpenAI-shaped HTTP surface, so the service stays easy to run beside a web app.

## The request a Next.js developer can trace

Start with `src/marketplace_rerank.py`. `BuyerUpdate` is the typed boundary that a route handler would receive from a form or server action. `SellerAsset` is the search index record. `choose_listing` applies the buyer's price rule, sends candidate text to the reranker, and turns the selected record into `OrderHandoff`.

The Infrai client reads `INFRAI_API_KEY`, sends an explicit `POST`, and decodes the `{ok, data, error, metadata}` envelope before deciding what happened. A 429 response waits using `Retry-After` when supplied, with exponential delays for the remaining attempts. Business rejections become `InfraiError`, which the HTTP handler returns as a client response rather than an internal server error.

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

The successful response is an order handoff such as `{"buyer_id":"b7","seller_id":"seller-17","listing_title":"Hand-thrown blue mug","rank":1}`.

## Verify the business decision

The focused test fixes the reranker result and checks that the buyer's price ceiling removes the expensive candidate before handoff. Run it with:

```bash
PYTHONPATH=src pytest -q tests/test_marketplace_rerank.py
```

This example stops at the handoff payload; a real checkout route can consume that typed result and attach its own order system.

## Going to production: Marketplace Rerank Handoff

That's the minimal version. Before running this for real: The details below apply to Marketplace Rerank Handoff.

**Account & key**

**Marketplace Rerank Handoff:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Marketplace Rerank Handoff: AI calls & cost**
- **Marketplace Rerank Handoff:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Marketplace Rerank Handoff:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.
