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
