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


def test_cli_delay_accepted_in_both_positions():
    from subito_scraper.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["--delay", "1.5", "regions"]).delay == 1.5
    assert parser.parse_args(["run", "--delay", "1.2"]).delay == 1.2
    assert parser.parse_args(["run"]).delay == 0.7


MOTORI = json.loads((Path(__file__).parent / "fixture_motori.json").read_text(encoding="utf-8"))


def test_normalize_car_and_bike():
    from subito_scraper.models import domain_of

    car = normalize(MOTORI["car"])
    assert car["domain"] == "motori" and car["propertyType"] == "car" and car["categoryId"] == 2
    assert car["brand"] and car["model"] and car["year"] and car["mileageKm"]
    assert car["fuel"] and car["gearbox"] and car["powerCv"] and car["powerKw"]
    assert "pricePerSqm" not in car and car["price"] > 0
    bike = normalize(MOTORI["bike"])
    assert bike["domain"] == "motori" and bike["propertyType"] == "motorbike"
    assert bike["brand"] == "Yamaha" and bike["year"] and bike["mileageKm"] is not None
    assert domain_of(7) == "realestate" and domain_of(3) == "motori"
    assert category_id("auto") == 2 == category_id("cars") and category_id("moto") == 3 and category_id("camper") == 34


class FakeValues:
    def brand(self, cid, name):
        return ("000083", "ALFA ROMEO") if cid == 2 else ("000015", "Yamaha")

    def model(self, cid, brand_key, name):
        return "000319" if name.lower() == "145" else None

    def key(self, list_name, name):
        return {"fuel": {"diesel": "2"}, "gearbox": {"automatico": "2"}, "car_type": {"suv": "5"}, "vehicle_status": {"km0": "2"}}[list_name][name.lower()]

    def mileage_key(self, kind, km):
        return "21" if kind == "max" else "1"


class FakeGeo:
    def resolve(self, region, province=None, town=None):
        return {"r": 4}


def test_vehicle_watch_params_and_queries():
    w = Watch(id="w", name="w", region="lombardia", category="auto", brand="Alfa Romeo", model="145", fuel="diesel", gearbox="automatico",
              body_type="suv", vehicle_status="km0", year_min=2015, year_max=2020, km_max=100000, hp_min=100, new_drivers=True, price_max=15000)
    params = w.api_params(FakeGeo(), FakeValues())
    assert params == {"c": 2, "t": "s", "r": 4, "pe": 15000, "cb": "000083", "cm": "000319", "fl": "2", "gr": "2", "ct": "5", "cvs": "2",
                      "ys": 2015, "ye": 2020, "me": "21", "hps": 100, "ndo": "true"}
    assert w.queries() == [None]
    # ambiguous model -> full-text query, combined with keywords when present
    w2 = Watch(id="w", name="w", category="auto", brand="Alfa Romeo", model="Giulietta", keywords=["unico proprietario"])
    p2 = w2.api_params(FakeGeo(), FakeValues())
    assert "cm" not in p2 and w2.queries() == ["Giulietta unico proprietario"]
    w3 = Watch(id="w", name="w", category="moto", brand="Yamaha", model="Ténéré 700")
    assert w3.api_params(FakeGeo(), FakeValues())["bb"] == "000015" and w3.queries() == ["Ténéré 700"]
    with pytest.raises(ValueError):
        Watch(id="w", name="w", category="appartamenti", brand="Fiat").api_params(FakeGeo(), FakeValues())


def test_vehicle_local_matching():
    car = normalize(MOTORI["car"])  # Alfa Romeo MiTo, diesel, manuale, 2011, 172000 km, 120 cv
    assert Watch(id="w", name="w", category="auto", brand="alfa romeo", model="mito").matches(car)
    assert not Watch(id="w", name="w", category="auto", brand="Fiat").matches(car)
    assert not Watch(id="w", name="w", category="auto", gearbox="automatico").matches(car)
    assert Watch(id="w", name="w", category="auto", fuel="gasolio").matches(car)
    assert not Watch(id="w", name="w", category="auto", year_min=2015).matches(car)
    assert not Watch(id="w", name="w", category="auto", km_max=100000).matches(car)
    assert Watch(id="w", name="w", category="auto", hp_min=100, hp_max=150).matches(car)
    assert not Watch(id="w", name="w", category="auto", exclude=["mito"]).matches(car)


def test_mileage_band_mapping():
    from subito_scraper.values import ValuesResolver

    class C:
        def get(self, url):
            if url.endswith("mileage/min"):
                return {"values": [{"key": "0", "value": "Km 0"}, {"key": "1", "value": "0"}, {"key": "2", "value": "5.000"}, {"key": "3", "value": "10.000"}, {"key": "21", "value": "100.000"}]}
            return {"values": [{"key": "0", "value": "Km 0"}, {"key": "1", "value": "4.999"}, {"key": "20", "value": "99.999"}, {"key": "21", "value": "109.999"}, {"key": "36", "value": "499.999"}]}

    v = ValuesResolver(C())
    assert v.mileage_key("min", 7000) == "2" and v.mileage_key("min", 0) == "1" and v.mileage_key("min", 999999) == "21"
    assert v.mileage_key("max", 100000) == "21" and v.mileage_key("max", 4000) == "1" and v.mileage_key("max", 999999) == "36"


def test_watch_color_keys():
    w = Watch.from_dict({"id": "a", "color": "#123456", "vehicle_color": "nero"})
    assert w.color_hex == "#123456" and w.color == "nero"
    w2 = Watch.from_dict({"id": "b", "color": "rosso"})
    assert w2.color == "rosso" and w2.color_hex is None


def test_dashboard_hides_orphans(tmp_path):
    rec = normalize(AD)
    with Store(tmp_path / "t.db") as store:
        store.upsert_listing(rec)
        store.record_match("old", rec["adId"])
        assert build_payload(store, [Watch(id="new", name="n")])["listings"] == []
        assert len(build_payload(store, [Watch(id="new", name="n")], include_orphans=True)["listings"]) == 1
        assert len(build_payload(store, [Watch(id="old", name="o")])["listings"]) == 1


def test_pack_uses_labels_not_levels():
    from subito_scraper.models import _pack

    feat = {"all": [
        {"key": "000103", "value": "TOYOTA", "level": 0, "label": "Marca"},
        {"key": "004796", "value": "Yaris Cross", "group_label": "Yaris Cross", "level": 1, "label": "Modello"},
        {"key": "000000", "value": "Altro allestimento", "level": 0, "label": "Versione"},
    ]}
    assert _pack(feat) == {"brand": "TOYOTA", "model": "Yaris Cross", "modelFull": "Yaris Cross", "version": None}


def test_commercial_vehicle_watch():
    class V(FakeValues):
        def key(self, list_name, name):
            if list_name == "vehicle_type":
                return {"furgone": "8", "camion": "1"}[name.lower()]
            return super().key(list_name, name)

    w = Watch(id="w", name="w", region="lombardia", category="veicoli-commerciali", body_type="furgone", brand="Iveco", model="Daily",
              year_min=2016, km_max=200000, price_max=25000, vat_deductible=True)
    params = w.api_params(FakeGeo(), V())
    # only type/status/vat/price go server-side; brand+model become the full-text query
    assert params == {"c": 4, "t": "s", "r": 4, "pe": 25000, "cvt": "8", "vatd": "true", "ys": 2016, "me": "21"}
    assert w.queries() == ["Iveco Daily"]
    rec = {"domain": "motori", "categoryId": 4, "title": "Iveco Daily 35C16 furgone", "description": "", "price": 19000, "year": 2019,
           "mileageKm": 120000, "vatDeductible": True, "bodyType": "Veicoli Commerciali fino a 35q", "advertType": "private"}
    assert w.matches(rec)
    assert not w.matches({**rec, "title": "Ford Transit"})
    assert not w.matches({**rec, "year": 2012})
    assert not w.matches({**rec, "mileageKm": 260000})
    assert not w.matches({**rec, "vatDeductible": False})
    assert w.matches({**rec, "vatDeductible": None})
