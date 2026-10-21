"""InvertirOnline API v2 responses, typed from real responses captured on 2026-10-21.

Only the fields we use are declared; unknown fields are ignored so a new field from IOL
doesn't break parsing, but a missing or retyped field we rely on fails loudly.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class IOLModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Token(BaseModel):
    """POST /token. expires_in comes as a string ("899")."""

    model_config = ConfigDict(extra="ignore")
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str


class Punta(IOLModel):
    """Best bid and ask."""

    cantidad_compra: float
    precio_compra: float
    precio_venta: float
    cantidad_venta: float


class Quote(IOLModel):
    """GET /api/v2/{mercado}/Titulos/{simbolo}/Cotizacion"""

    ultimo_precio: float
    variacion: float
    apertura: float
    maximo: float
    minimo: float
    fecha_hora: datetime
    cierre_anterior: float
    monto_operado: float
    volumen_nominal: float
    moneda: str
    puntas: list[Punta] | None = None
    cantidad_operaciones: int
    descripcion_titulo: str | None = None
    plazo: str | None = None


class HistoryPoint(IOLModel):
    """One row of GET .../Cotizacion/seriehistorica/{desde}/{hasta}/{ajustada|sinAjustar}.

    "ajustada" gives one row per day but only for local stocks; "sinAjustar" covers CEDEARs
    and bonds too but returns several intraday rows per day.
    """

    ultimo_precio: float
    apertura: float
    maximo: float
    minimo: float
    fecha_hora: datetime
    monto_operado: float
    volumen_nominal: float


class DailyBar(BaseModel):
    """Our own daily candle, built from HistoryPoint rows."""

    day: date
    open: float
    high: float
    low: float
    close: float


class Titulo(IOLModel):
    simbolo: str
    descripcion: str
    pais: str
    mercado: str
    tipo: str  # "ACCIONES", "CEDEARS", "TitulosPublicos", ...
    plazo: str
    moneda: str


class Activo(IOLModel):
    cantidad: float
    comprometido: float
    ultimo_precio: float
    ppc: float  # average purchase price
    ganancia_porcentaje: float
    ganancia_dinero: float
    valorizado: float
    variacion_diaria: float
    titulo: Titulo


class Portafolio(IOLModel):
    """GET /api/v2/portafolio/{pais}"""

    pais: str
    activos: list[Activo]


class Saldo(IOLModel):
    liquidacion: str
    saldo: float
    comprometido: float
    disponible: float
    disponible_operar: float


class Cuenta(IOLModel):
    numero: str
    tipo: str
    moneda: str
    disponible: float
    comprometido: float
    saldo: float
    titulos_valorizados: float
    total: float
    saldos: list[Saldo]
    estado: str


class EstadoCuenta(IOLModel):
    """GET /api/v2/estadocuenta"""

    cuentas: list[Cuenta]
    total_en_pesos: float


class Operacion(IOLModel):
    """GET /api/v2/operaciones"""

    numero: int
    fecha_orden: datetime
    tipo: str  # "Compra", "Venta", "Pago de Dividendos", "Rescate FCI", ...
    estado: str
    mercado: str
    simbolo: str
    cantidad: float | None = None
    monto: float | None = None
    modalidad: str
    precio: float | None = None
    fecha_operada: datetime | None = None
    cantidad_operada: float | None = None
    precio_operado: float | None = None
    monto_operado: float | None = None
    plazo: str


class OptionQuote(IOLModel):
    ultimo_precio: float
    variacion: float
    fecha_hora: datetime
    volumen_nominal: float
    cantidad_operaciones: int


class Opcion(IOLModel):
    """GET /api/v2/{mercado}/Titulos/{simbolo}/Opciones"""

    cotizacion: OptionQuote
    simbolo_subyacente: str
    fecha_vencimiento: datetime
    tipo_opcion: Literal["Call", "Put"]
    simbolo: str
    descripcion: str


class PanelTitulo(IOLModel):
    simbolo: str
    descripcion: str
    puntas: Punta | None = None
    ultimo_precio: float
    variacion_porcentual: float
    apertura: float
    maximo: float
    minimo: float
    ultimo_cierre: float
    volumen: float
    cantidad_operaciones: float
    fecha: datetime
    moneda: str


class Panel(IOLModel):
    """GET /api/v2/Cotizaciones/{instrumento}/{panel}/{pais}, e.g. acciones/merval, bonos/todos."""

    titulos: list[PanelTitulo]


class CaucionRate(IOLModel):
    plazo: int  # days
    monto_contado: float
    tasa_promedio: float  # annual %, e.g. 19.4
    fecha_vencimiento: datetime


class CaucionPanel(IOLModel):
    """GET /api/v2/Cotizaciones/cauciones/todas/argentina"""

    titulos: list[CaucionRate]
