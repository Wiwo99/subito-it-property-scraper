import json
from pathlib import Path

import pytest

from subito_scraper.dashboard import PLACEHOLDER, build_payload, render
from subito_scraper.geo import region_id, slugify
from subito_scraper.models import CATEGORIES, ad_type_key, category_id, normalize, parse_urn
from subito_scraper.store import Store
from subito_scraper.watches import Watch, contains, load_watches, normalize_text

FIXTURE = json.loads((Path(__file__).parent / "fixture_search.json").read_text(encoding="utf-8"))
AD = FIXTURE["ads"][0]


def test_parse_urn():
    assert parse_urn("id:ad:612233839:list:659035166") == ("612233839", "659035166")
    assert parse_urn("") == (None, None)


def test_normalize_core_fields():
    rec = normalize(AD, search={"region": "umbria", "query": "bilocale", "watch": "w1"}, scraped_at="2026-09-02T00:00:00+00:00")
    assert rec["adId"] == "659035166"
    assert rec["detailUrl"].startswith("https://www.subito.it/appartamenti/")
    assert rec["transactionType"] == "sale"
    assert rec["propertyType"] == "apartment"
    assert rec["price"] == 165000
    assert rec["areaSqm"] == 49
    assert rec["pricePerSqm"] == round(165000 / 49)
    assert rec["rooms"] == 2
    assert rec["bathrooms"] == 1
    assert rec["energyClass"] == "A4"
    assert rec["hasElevator"] is True
    assert rec["hasGarden"] is True
    assert rec["hasParking"] is True
    assert rec["advertType"] == "agency"
    assert rec["advertiserName"] == "Gabetti Perugia 1"
    assert rec["region"] == "Umbria" and rec["province"] == "Perugia" and rec["provinceCode"] == "PG"
    assert rec["city"] == "Corciano"
    assert rec["latitude"] and rec["longitude"]
    assert rec["imageCount"] == 8 and rec["mainImageUrl"].startswith("https://")
    assert rec["searchKeyword"] == "bilocale" and rec["searchWatch"] == "w1"
    assert rec["scrapedAt"] == "2026-09-02T00:00:00+00:00"


def test_lookups():
    assert category_id("appartamenti") == 7 == category_id("apartment") == category_id(7)
    assert category_id("ville") == 29
    assert ad_type_key("affitto") == "u" and ad_type_key("sale") == "s"
    with pytest.raises(ValueError):
        category_id("castelli")
    assert region_id("Lombardia") == 4 and region_id("italia") is None
    assert slugify("Valle d'Aosta") == "valle-d-aosta"
    assert set(CATEGORIES) >= {7, 29, 30, 31, 32, 8, 43, 33}


def test_keyword_matching():
    assert contains(normalize_text("Bilocale, luminoso"), "bilocale")
    assert not contains(normalize_text("bilocalexyz"), "bilocale")
    assert contains(normalize_text("appartamento ristrutturato"), "ristruttur*")
    assert contains(normalize_text("Nuda proprietà"), "nuda proprieta")
    w = Watch(id="w", name="w", keywords=["bilocale"], exclude=["asta"], all=["giardino"], price_max=200000)
    rec = normalize(AD)
    assert w.matches(rec)
    assert not Watch(id="w", name="w", keywords=["trilocale"]).matches(rec)
    assert not Watch(id="w", name="w", keywords=["bilocale"], exclude=["detrazione"]).matches(rec)
    assert not Watch(id="w", name="w", keywords=["bilocale"], price_max=100000).matches(rec)
    assert not Watch(id="w", name="w", keywords=["bilocale"], advertiser="private").matches(rec)
    assert Watch(id="w", name="w", keywords=["corciano"], title_only=True).matches(rec)
    assert not Watch(id="w", name="w", keywords=["solomeo"], title_only=True).matches(rec)


def test_watch_queries_and_params():
    w = Watch(id="w", name="w", region="toscana", keywords=["Bilocale", "bilocale ", "attico"], price_min=1, price_max=2, title_only=True)

    class FakeGeo:
        def resolve(self, region, province=None, town=None):
            return {"r": 9}

    assert w.queries() == ["Bilocale", "attico"]
    params = w.api_params(FakeGeo())
    assert params == {"c": 7, "t": "s", "r": 9, "ps": 1, "pe": 2, "qso": "true"}


def test_load_watches(tmp_path):
    path = tmp_path / "w.json"
    path.write_text(json.dumps({"defaults": {"max_items": 5}, "watches": [{"name": "Casa Bergamo", "keywords": "terrazzo", "foo": 1}]}))
    (w,) = load_watches(path)
    assert w.id == "casa-bergamo" and w.max_items == 5 and w.keywords == ["terrazzo"]
    path.write_text(json.dumps([{"id": "a"}, {"id": "a"}]))
    with pytest.raises(ValueError):
        load_watches(path)


def test_store_roundtrip(tmp_path):
    rec = normalize(AD, scraped_at="2026-09-01T00:00:00+00:00")
    with Store(tmp_path / "t.db") as store:
        assert store.upsert_listing(rec, "2026-09-01T00:00:00+00:00") == ("new", None)
        assert store.record_match("w1", rec["adId"], "2026-09-01T00:00:00+00:00") is True
        assert store.record_match("w1", rec["adId"], "2026-09-01T01:00:00+00:00") is False
        assert store.upsert_listing(rec, "2026-09-01T02:00:00+00:00") == ("seen", 165000)
        cheaper = dict(rec, price=150000)
        assert store.upsert_listing(cheaper, "2026-09-02T00:00:00+00:00") == ("price_changed", 165000)
        run = store.start_run(None)
        store.finish_run(run, fetched=1, matched=1, new_count=1)
        listings = store.listings(watch_id="w1")
        assert len(listings) == 1 and listings[0]["price"] == 150000 and listings[0]["firstSeen"] == "2026-09-01T00:00:00+00:00"
        assert [h["price"] for h in store.price_history()[rec["adId"]]] == [165000, 150000]
        assert store.counts() == {"listings": 1, "matches": 1}
        payload = build_payload(store, [Watch(id="w1", name="Watch 1")])
        assert payload["watches"][0]["count"] == 1
        listing = payload["listings"][0]
        assert listing["priceDelta"] == -15000 and listing["previousPrice"] == 165000 and listing["watches"] == ["w1"]
        assert store.prune("2026-09-03T00:00:00+00:00") == 1
        assert store.counts()["listings"] == 0


def test_render_embeds_data(tmp_path):
    template = tmp_path / "t.html"
    template.write_text("<script>" + PLACEHOLDER + "</script>")
    html = render({"listings": [{"title": "</script><b>x"}]}, template)
    assert "window.__DASHBOARD_DATA__" in html
    assert "</script><b>" not in html.split("window.__DASHBOARD_DATA__")[1]
