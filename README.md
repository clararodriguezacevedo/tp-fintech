# Tecnología para las Finanzas: portfolio advisor

Combina noticias recientes, mercados de predicción (Polymarket y Kalshi) y la API de
InvertirOnline (IOL) para recomendar **comprar / vender / mantener** sobre los tickers del
mercado argentino (acciones, CEDEARs, bonos).

## Flujo

1. **Recolectar** cada pocos minutos: noticias (GDELT + RSS), mercados de Polymarket y Kalshi,
   y el cambio de probabilidad de cada mercado (no solo su nivel).
2. **Vincular**: un LLM gratuito (Gemini Flash-Lite, free tier) etiqueta cada ítem con los tickers que
   afecta, la dirección esperada y un resumen corto.
3. **Puntuar**: combina sentimiento de noticias, cambios de probabilidad y técnicos simples en
   una señal con confianza. Cada recomendación muestra la evidencia en la que se basa.
4. **Portfolio**: lo mismo al revés, para cada ticker que el usuario ya tiene.
5. **Compra en un click**: pantalla de confirmación con monto, precio, stop loss y take profit
   ya calculados, después la orden, después el SL/TP.

## Funcionalidades

- **Track record**: se guarda cada recomendación y se compara contra el cierre del día
  siguiente. Tasa de acierto por tipo de señal.
- **SL/TP según volatilidad**: distancia en base al ATR de cada ticker, y tamaño de la
  posición para que un stop-out pierda un % fijo del portfolio.
- **Dólar MEP / CCL**: calculado con bonos (AL30 vs AL30D / AL30C). Para cada CEDEAR se separa
  cuánto del movimiento es la acción y cuánto es el dólar, en una frase simple.
- **Caución para la plata parada**: si nada puntúa lo suficiente para comprar, sugerir
  caución a la tasa actual.
- **Cobertura con opciones**: para un ticker en cartera con señal fuerte de venta, sugerir un
  put protectivo de la cadena de opciones.
- **Alertas de apuestas grandes**: trades grandes recientes en Polymarket sobre mercados que
  afectan a los tickers del usuario.
- **Polymarket vs Kalshi**: cuando ambos listan el mismo evento con probabilidades distintas,
  se muestran los dos (medida de incertidumbre).
- **Mercados argentinos**: filtro de mercados sobre elecciones, FMI, inflación y Fed,
  mapeados a Merval, bonos y ADRs.
- **Horario de mercado**: BYMA opera de 11:00 a 17:00 (ART). Fuera de horario las compras
  quedan en cola y se muestra el pronóstico para el día siguiente.
- **Vista de portfolio**: treemap con alertas de concentración, más la tarjeta resumen de cada
  noticia y mercado.

## Stack

| Parte | Tecnología |
| --- | --- |
| Backend | Python 3.12, FastAPI, `uv` |
| Base de datos | Supabase (Postgres hosteado) |
| Tareas periódicas | APScheduler (corre dentro del proceso de FastAPI) |
| LLM | Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`), free tier |
| Frontend | Next.js + Tailwind |
| Broker | IOL: lecturas contra la API real; compras en **paper trading** por defecto (simuladas con precios reales de IOL), órdenes reales solo con `IOL_LIVE_TRADING=true` |

## Estructura

```
backend/     API FastAPI, clientes de datos, scoring, jobs
frontend/    app Next.js
supabase/    migraciones SQL
```

## Cómo correrlo

```bash
cp backend/.env.example backend/.env   # completar las claves
cd backend && uv sync && uv run uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

El esquema de la base está en `supabase/migrations/`. Para aplicar las migraciones pendientes
(necesita `DATABASE_URL` en `backend/.env`):

```bash
cd backend && uv run python scripts/migrate.py
```

## Tareas programadas (GitHub Actions)

Los jobs corren en GitHub Actions, no en el proceso de la API (`.github/workflows/`):

| Workflow | Cuándo (hora Argentina) | Qué hace |
| --- | --- | --- |
| `collect` | cada 10 minutos | junta mercados y noticias, los etiqueta con Gemini, actualiza las recomendaciones live |
| `trades` | cada 5 minutos, lunes a viernes de 11 a 17 | llena compras en cola y revisa stop loss / take profit del paper trading |
| `after close` | 17:30, lunes a viernes | califica las recomendaciones del día y emite las del día siguiente |

Las claves están en los Secrets del repo (`SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`,
`IOL_USERNAME`, `IOL_PASSWORD`). Las órdenes reales siguen bloqueadas salvo que se cree la
variable de repo `IOL_LIVE_TRADING=true`.

Para correr un job a mano: pestaña Actions del repo > workflow > *Run workflow*, o localmente
`cd backend && uv run python -m scripts.run_job {cycle|trades|after-close}`.

GitHub demora los crons a veces (de unos minutos a media hora en horas pico) y desactiva los
workflows programados de un repo público después de 60 días sin commits.

## Tipado

- **APIs externas**: cada respuesta de IOL, Polymarket, Kalshi y GDELT se valida con modelos
  Pydantic en `backend/app/models/`, armados a partir de respuestas reales. Si una API cambia
  un campo que usamos, falla al parsear y no más adelante.
- **Base de datos y API propia**: las filas de Supabase se validan con `backend/app/models/db.py`
  y cada endpoint declara su `response_model`, así que `/openapi.json` describe todo.
- **Frontend**: los esquemas zod de `frontend/src/lib/api/schemas.ts` se generan desde ese
  OpenAPI, y `frontend/src/lib/api/client.ts` valida cada respuesta con ellos.
- **Chequeo estático**: `pyright` en el backend y `tsc` en el frontend.

Después de cambiar un modelo del backend:

```bash
cd backend && uv run python -m scripts.export_openapi
cd frontend && npm run gen:api && npm run typecheck
cd backend && uv run pyright
```

## Recomendaciones y track record

Cada ciclo calcula un puntaje por ticker (ver `backend/app/analysis/scoring.py`) que combina
noticias (con decaimiento por antigüedad), el movimiento en 24 h de los mercados de predicción
(contando cada evento una sola vez) y la tendencia del precio. Los tickers en cartera solo
pueden recibir vender o mantener; el resto, comprar o mantener.

A las 17:30 se califican las recomendaciones del día contra el cierre y se emiten las del día
siguiente. Comprar acierta si el precio sube, vender si baja, mantener si se mueve menos de
1,5%. `GET /track-record` muestra la tasa de acierto por acción, por señal dominante, por
confianza y por si el ticker estaba en cartera.

## Paper trading

IOL no ofrece un sandbox utilizable, así que con `IOL_LIVE_TRADING=false` (el valor por
defecto) las compras se simulan: se registran en `trade_intents`, se llenan al último precio
real de IOL si BYMA está abierto (si no, quedan en cola hasta la apertura) y un job revisa cada
minuto el stop loss y el take profit. El resultado de cada operación alimenta el track record.
