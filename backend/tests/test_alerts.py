"""The three alert triggers reach app.alerts.send with the right subject and a once-only key."""

from types import SimpleNamespace

from app import alerts, jobs


def capture(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send", lambda key, subject, lines: sent.append((key, subject)) or True)
    return sent


def rec(ticker, action, held):
    return SimpleNamespace(ticker=ticker, action=action, held=held, score=-0.6, evidence=[])


def test_sell_signal_only_for_held_positions(monkeypatch):
    sent = capture(monkeypatch)
    from datetime import date

    alerts.sell_signals([rec("VIST", "sell", True), rec("GGAL", "sell", False), rec("KO", "keep", True)], date(2026, 10, 28))
    assert sent == [("sell:VIST:2026-10-28", "Vender VIST: la recomendación cambió")]


def test_failed_job_step_sends_one_alert_per_step(monkeypatch):
    sent = capture(monkeypatch)

    def boom():
        raise RuntimeError("IOL down")

    failed = jobs._alert_failures("collect", jobs._run_all([("ok", lambda: None), ("refresh_holdings", boom)]))
    assert failed == ["refresh_holdings"]
    assert [s[1] for s in sent] == ["Falló un paso del job collect: refresh_holdings"]
    assert sent[0][0].startswith("fail:refresh_holdings:")


def test_gemini_quota_error_sends_alert(monkeypatch):
    from google.genai import errors

    from app.analysis import tagger

    sent = capture(monkeypatch)

    class Quota(errors.APIError):
        def __init__(self):
            self.code = 429

        def __str__(self):
            return "429 RESOURCE_EXHAUSTED"

    def raise_quota(**_):
        raise Quota()

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=raise_quota))
    monkeypatch.setattr(tagger, "_get_client", lambda: fake)
    assert tagger.tag_items([tagger.TagInput(id="a", kind="news", title="t")]) == []
    assert [s[1] for s in sent] == ["Se agotó la cuota gratis de Gemini"]


def test_send_goes_out_once_per_key(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts, "get_settings", lambda: SimpleNamespace(
        resend_api_key="re_x", alert_email="a@b.c", alert_from="x <x@y.z>", site_url=""))
    seen: set[str] = set()
    monkeypatch.setattr(alerts, "_already_sent", lambda key: key in seen)

    class Resp:
        def raise_for_status(self):
            return self

    monkeypatch.setattr(alerts.httpx, "post", lambda *a, **k: calls.append(k["json"]["subject"]) or Resp())

    class DB:
        def table(self, _):
            return self

        def insert(self, row):
            seen.add(row["key"])
            return self

        def execute(self):
            return self

    monkeypatch.setattr(alerts, "get_db", lambda: DB())
    assert alerts.send("k", "Hola", ["x"]) is True
    assert alerts.send("k", "Hola", ["x"]) is False
    assert calls == ["Hola"]


def test_gdelt_failures_never_stop_the_news(monkeypatch):
    import httpx

    from app.sources import news

    def timeout(*_a, **_k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(news, "_fetch_gdelt", timeout)
    assert news.fetch_gdelt(httpx.Client()) == []

    def bad_json(*_a, **_k):
        raise ValueError("Expecting value")

    monkeypatch.setattr(news, "_fetch_gdelt", bad_json)
    assert news.fetch_gdelt(httpx.Client()) == []


def test_breakdown_with_an_event_date_can_be_saved():
    import json
    from datetime import date

    from app.models.db import SignalBreakdown

    b = SignalBreakdown(news=0, markets=0, event_kind="dividend", event_date=date(2026, 10, 30))
    assert json.loads(json.dumps(b.model_dump(mode="json")))["event_date"] == "2026-10-30"


def test_garbled_ids_and_unknown_tickers_are_dropped(monkeypatch):
    from app.analysis import tagger

    answer = tagger.TagBatch(items=[
        tagger.TaggedItem(id="news-1", summary="Sube.", impacts=[
            tagger.TickerImpact(ticker="ASML", direction="up", mention="ASML", reason="r"),
            tagger.TickerImpact(ticker="INVENTADO", direction="up", mention="ASML", reason="r"),
        ]),
        tagger.TaggedItem(id="news-1x", summary="Id roto.", impacts=[]),
    ])
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(parsed=answer)))
    monkeypatch.setattr(tagger, "_get_client", lambda: fake)
    got = tagger.tag_items([tagger.TagInput(id="news-1", kind="news", title="ASML sube")], universe={"ASML": "Asml Holding Nv"})
    assert [i.id for i in got] == ["news-1"]
    assert [x.ticker for x in got[0].impacts] == ["ASML"]


def test_an_item_left_out_of_a_good_answer_counts_as_seen(monkeypatch):
    from app.analysis import tagger

    answer = tagger.TagBatch(items=[tagger.TaggedItem(id="a", summary="Sube.", impacts=[])])
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(parsed=answer)))
    monkeypatch.setattr(tagger, "_get_client", lambda: fake)
    got = tagger.tag_items([tagger.TagInput(id=i, kind="news", title="t") for i in "ab"])
    assert sorted(i.id for i in got) == ["a", "b"]


def test_market_reasons_say_how_the_probability_moved():
    down = SimpleNamespace(kind="market", contribution=-0.4, direction="up", reason="Petróleo caro ayuda a VIST.")
    up = SimpleNamespace(kind="market", contribution=0.4, direction="up", reason="Petróleo caro ayuda a VIST.")
    # A market betting on a fall: its probability falling is good news for the ticker.
    bet_on_fall = SimpleNamespace(kind="market", contribution=0.4, direction="down", reason="Apuesta a la baja.")
    news = SimpleNamespace(kind="news", contribution=-0.4, direction="down", reason="Mala noticia.")
    assert alerts.evidence_text(down).startswith("Bajó la probabilidad")
    assert alerts.evidence_text(up).startswith("Subió la probabilidad")
    assert alerts.evidence_text(bet_on_fall).startswith("Bajó la probabilidad")
    assert alerts.evidence_text(news) == "Mala noticia."


def test_other_broken_accents_are_caught_and_entities_repaired(monkeypatch):
    from app.analysis import tagger

    answer = tagger.TagBatch(items=[
        tagger.TaggedItem(id="a", summary="La inversi&oacute;n crece.", impacts=[]),
        tagger.TaggedItem(id="b", summary="El plan econ##mico.", impacts=[]),
    ])
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(parsed=answer)))
    monkeypatch.setattr(tagger, "_get_client", lambda: fake)
    got = tagger.tag_items([tagger.TagInput(id=i, kind="news", title="t") for i in "ab"])
    assert [(i.id, i.summary) for i in got] == [("a", "La inversión crece.")]
