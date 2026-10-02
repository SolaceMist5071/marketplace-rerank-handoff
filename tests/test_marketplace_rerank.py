import json

from marketplace_rerank import BuyerUpdate, InfraiReranker, SellerAsset, choose_listing


class StubReranker(InfraiReranker):
    def rerank(self, query, candidates, top_k=3):
        assert query == "blue coffee mug"
        assert len(candidates) == 1
        return [0]


def test_buyer_update_produces_order_handoff():
    assets = [
        SellerAsset("s1", "Blue mug", "Ceramic coffee cup", 2500),
        SellerAsset("s2", "Blue mug", "Travel tumbler", 3200),
    ]
    handoff = choose_listing(BuyerUpdate("b7", "blue coffee mug", 3000), assets, StubReranker())
    assert handoff.seller_id == "s1"
    assert handoff.listing_title == "Blue mug"
    assert handoff.rank == 1


def test_infrai_rerank_reads_ranked_response_without_forcing_vendor():
    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"ok":true,"data":{"ranked":[{"index":1,"score":0.9}]}}'

    def opener(request, timeout):
        assert json.loads(request.data) == {"query": "mug", "candidates": ["a", "b"], "top_k": 1}
        return Response()

    assert InfraiReranker("key", opener).rerank("mug", ["a", "b"], 1) == [1]
