"""E-mail alerts through Resend (https://resend.com, free tier).

Sent when something the user holds turns to "sell", when a job step fails, and when Gemini's
free quota runs out. Each alert has a key and goes out once (alerts_sent). Without
RESEND_API_KEY and ALERT_EMAIL nothing is sent; the alert is only logged.
"""

import html
import logging
from datetime import date

import httpx

from app.analysis import market_hours
from app.config import get_settings
from app.db import get_db

log = logging.getLogger(__name__)

RESEND = "https://api.resend.com/emails"


def _already_sent(key: str) -> bool:
    return bool(get_db().table("alerts_sent").select("key").eq("key", key).execute().data)


def send(key: str, subject: str, lines: list[str]) -> bool:
    """Send once per key. Returns whether an e-mail went out."""
    s = get_settings()
    if not s.resend_api_key or not s.alert_email:
        log.info("alert not sent (no RESEND_API_KEY or ALERT_EMAIL): %s", subject)
        return False
    try:
        if _already_sent(key):
            return False
        body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
        if s.site_url:
            body += f'<p><a href="{html.escape(s.site_url)}">Abrir El Parqué</a></p>'
        r = httpx.post(
            RESEND, timeout=20, headers={"Authorization": f"Bearer {s.resend_api_key}"},
            json={"from": s.alert_from, "to": [s.alert_email], "subject": subject, "html": body},
        )
        r.raise_for_status()
        get_db().table("alerts_sent").insert({"key": key, "subject": subject}).execute()
        log.info("alert sent: %s", subject)
        return True
    except Exception:
        log.exception("could not send alert: %s", subject)
        return False


def _today() -> date:
    return market_hours.now_art().date()


def sell_signals(recs: list, target: date) -> None:
    """recs: scoring.Recommendation. One e-mail per held ticker and target day."""
    for r in recs:
        if not (r.held and r.action == "sell"):
            continue
        reasons = [e.reason for e in r.evidence[:3] if e.reason]
        send(
            f"sell:{r.ticker}:{target.isoformat()}",
            f"Vender {r.ticker}: la recomendación cambió",
            [f"Para {r.ticker}, que tenés en cartera, ahora la recomendación es vender "
             f"(puntaje {r.score:+.2f})."] + [f"Por qué: {x}" for x in reasons],
        )


def job_failed(job: str, steps: list[str]) -> None:
    for step in steps:
        send(
            f"fail:{step}:{_today().isoformat()}",
            f"Falló un paso del job {job}: {step}",
            [f"El paso {step} del job {job} falló hoy. Los demás pasos siguieron corriendo.",
             "Revisá los logs de Vercel (tp-fintech-api) para ver el error."],
        )


def gemini_quota() -> None:
    send(
        f"gemini-quota:{_today().isoformat()}",
        "Se agotó la cuota gratis de Gemini",
        ["Gemini respondió 429 (cuota agotada). Las noticias nuevas quedan sin etiquetar y se "
         "etiquetan en los próximos ciclos, cuando se renueve la cuota.",
         "Mientras tanto las recomendaciones usan solo lo que ya estaba etiquetado."],
    )
