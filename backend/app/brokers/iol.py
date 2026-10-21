"""InvertirOnline API v2 client.

Auth: POST /token with a password grant returns a bearer token valid for 15 minutes plus a
refresh token. Reads always use the real API (IOL's sandbox is not available). buy() and
sell() refuse to run unless IOL_LIVE_TRADING=true; otherwise trades are simulated by
app.trading.paper.

Endpoint paths follow the public IOL v2 docs (https://api.invertironline.com/Help). Check each
one against the docs the first time it runs, since IOL does not publish an OpenAPI file.
"""

import time
from datetime import date, timedelta

import httpx

from app.config import get_settings

BASE_URL = "https://api.invertironline.com"


class LiveTradingDisabled(RuntimeError):
    pass


class IOLClient:
    def __init__(self, username: str, password: str, live: bool = False):
        self.base = BASE_URL
        self.live = live
        self._username, self._password = username, password
        self._token: str | None = None
        self._refresh: str | None = None
        self._expires_at = 0.0
        self._http = httpx.Client(base_url=self.base, timeout=20)

    # Auth

    def _auth(self, data: dict) -> None:
        r = self._http.post("/token", data=data)
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._refresh = body.get("refresh_token")
        # Renew a minute early so a request never goes out with an expired token.
        self._expires_at = time.time() + int(body.get("expires_in", 900)) - 60

    def _ensure_token(self) -> None:
        if self._token and time.time() < self._expires_at:
            return
        if self._refresh:
            try:
                self._auth({"grant_type": "refresh_token", "refresh_token": self._refresh})
                return
            except httpx.HTTPStatusError:
                pass
        self._auth(
            {"grant_type": "password", "username": self._username, "password": self._password}
        )

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        self._ensure_token()
        r = self._http.request(
            method, path, headers={"Authorization": f"Bearer {self._token}"}, **kwargs
        )
        r.raise_for_status()
        return r.json()

    # Account

    def account_status(self) -> dict:
        return self._request("GET", "/api/v2/estadocuenta")

    def portfolio(self, country: str = "argentina") -> dict:
        return self._request("GET", f"/api/v2/portafolio/{country}")

    def operations(self) -> list:
        return self._request("GET", "/api/v2/operaciones")

    def operation(self, number: int) -> dict:
        return self._request("GET", f"/api/v2/operaciones/{number}")

    def cancel_operation(self, number: int) -> dict:
        if not self.live:
            raise LiveTradingDisabled("real orders are off; set IOL_LIVE_TRADING=true to enable")
        return self._request("DELETE", f"/api/v2/operaciones/{number}")

    # Market data

    def quote(self, symbol: str, market: str = "bCBA") -> dict:
        return self._request("GET", f"/api/v2/{market}/Titulos/{symbol}/Cotizacion")

    def history(self, symbol: str, start: date, end: date, market: str = "bCBA") -> list:
        return self._request(
            "GET",
            f"/api/v2/{market}/Titulos/{symbol}/Cotizacion/seriehistorica/"
            f"{start.isoformat()}/{end.isoformat()}/ajustada",
        )

    def options(self, symbol: str, market: str = "bCBA") -> list:
        return self._request("GET", f"/api/v2/{market}/Titulos/{symbol}/Opciones")

    def panel(self, instrument: str, panel: str, country: str = "argentina") -> dict:
        """e.g. panel("acciones", "merval"), panel("cedears", "todos"), panel("cauciones", "todas")."""
        return self._request("GET", f"/api/v2/Cotizaciones/{instrument}/{panel}/{country}")

    # Orders

    def _order(self, side: str, symbol: str, quantity: int, price: float, market: str) -> dict:
        if not self.live:
            raise LiveTradingDisabled("real orders are off; set IOL_LIVE_TRADING=true to enable")
        body = {
            "mercado": market,
            "simbolo": symbol,
            "cantidad": quantity,
            "precio": price,
            "plazo": "t1",
            "validez": (date.today() + timedelta(days=1)).isoformat(),
            "tipoOrden": "precioLimite",
        }
        return self._request("POST", f"/api/v2/operar/{side}", json=body)

    def buy(self, symbol: str, quantity: int, price: float, market: str = "bCBA") -> dict:
        return self._order("Comprar", symbol, quantity, price, market)

    def sell(self, symbol: str, quantity: int, price: float, market: str = "bCBA") -> dict:
        return self._order("Vender", symbol, quantity, price, market)


_client: IOLClient | None = None


def get_iol() -> IOLClient:
    global _client
    if _client is None:
        s = get_settings()
        if not s.iol_username or not s.iol_password:
            raise RuntimeError("IOL_USERNAME and IOL_PASSWORD must be set in backend/.env")
        _client = IOLClient(s.iol_username, s.iol_password, live=s.iol_live_trading)
    return _client
