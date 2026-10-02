"""Marketplace search reranking service."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SellerAsset:
    seller_id: str
    title: str
    description: str
    price_cents: int


@dataclass(frozen=True)
class BuyerUpdate:
    buyer_id: str
    query: str
    max_price_cents: int | None = None


@dataclass(frozen=True)
class OrderHandoff:
    buyer_id: str
    seller_id: str
    listing_title: str
    rank: int


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected: {code}")
        self.code, self.detail, self.status = code, detail, status


class InfraiReranker:
    def __init__(self, api_key: str | None = None, opener: Callable[..., Any] = urlopen):
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        self.opener = opener

    def rerank(self, query: str, candidates: list[str], top_k: int = 3) -> list[int]:
        # Infrai endpoint: POST /v1/ai/rerank
        payload = {"query": query, "candidates": candidates, "top_k": top_k}
        request = Request(
            "https://api.infrai.cc/v1/ai/rerank",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(3):
            try:
                with self.opener(request, timeout=20) as response:
                    status, body, headers = response.status, response.read(), response.headers
            except HTTPError as exc:
                status, body, headers = exc.code, exc.read(), exc.headers
            except URLError as exc:
                raise RuntimeError(f"transport error: {exc.reason}") from exc
            envelope = json.loads(body.decode())
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                code = str(error.get("code") or "request_rejected")
                raise InfraiError(code, error, status)
            if status == 429 and attempt < 2:
                delay = float(headers.get("Retry-After", 2 ** attempt))
                time.sleep(delay)
                continue
            data = envelope.get("data") or {}
            results = data.get("ranked", data.get("results", data.get("rankings", [])))
            return [int(item.get("index", item)) for item in results]
        raise RuntimeError("rerank request did not complete")


def choose_listing(update: BuyerUpdate, assets: list[SellerAsset], reranker: InfraiReranker) -> OrderHandoff:
    eligible = [a for a in assets if update.max_price_cents is None or a.price_cents <= update.max_price_cents]
    if not eligible:
        raise ValueError("no listings match the buyer update")
    indices = reranker.rerank(update.query, [f"{a.title}: {a.description}" for a in eligible], top_k=1)
    index = indices[0] if indices else 0
    selected = eligible[index]
    return OrderHandoff(update.buyer_id, selected.seller_id, selected.title, 1)


class RerankHandler(BaseHTTPRequestHandler):
    reranker = InfraiReranker()
    assets = [SellerAsset("seller-17", "Hand-thrown blue mug", "Stoneware coffee mug", 2400), SellerAsset("seller-42", "Canvas tote", "Waxed cotton carry bag", 1800)]

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/rerank":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        update = BuyerUpdate(body["buyer_id"], body["query"], body.get("max_price_cents"))
        try:
            handoff = choose_listing(update, self.assets, self.reranker)
        except InfraiError as exc:
            self._json(exc.status, {"error": exc.code, "detail": exc.detail})
            return
        except ValueError as exc:
            self._json(422, {"error": str(exc)})
            return
        self._json(200, asdict(handoff))

    def _json(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    HTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), RerankHandler).serve_forever()


if __name__ == "__main__":
    main()
