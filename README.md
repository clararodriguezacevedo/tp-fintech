# Tecnología para las Finanzas: portfolio advisor

Combina noticias recientes, mercados de predicción (Polymarket y Kalshi) y la API de
IOL Inversiones (https://developers.iolinversiones.com) para recomendar **comprar / vender / mantener** sobre los tickers del
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
| Tareas periódicas | GitHub Actions (cron) |
| LLM | Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`), free tier |
| Frontend | Next.js + Tailwind, en Vercel |
| Backend en producción | Vercel (función serverless) |
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

## Frontend

"El Parqué": Next.js (App Router) con páginas renderizadas en el servidor. Diseño simple, pensado
para alguien sin experiencia: primero qué hacer, después por qué y al final el detalle.

| Página | Qué muestra |
| --- | --- |
| `/` Hoy | qué comprar (con la razón principal) y qué hacer con cada posición de la cartera |
| `/cartera` | valor, qué vender, posiciones con su peso en la cartera y valor en el tiempo |
| `/ticker/[símbolo]` | recomendación, por qué, compra en un click con stop loss y take profit, y precio de 3 meses |
| `/operaciones` | mis compras (simuladas): estado, resultado, cancelar o vender |
| `/historial` | cuántas recomendaciones acertaron y el detalle día por día |
| `/noticias` | últimas noticias y lo que esperan los mercados de predicción |

Arriba de todo hay una cinta con las recomendaciones del día.

El sitio está en **https://tp-fintech-web.vercel.app** y pide contraseña en `/login`, porque
muestra la cartera real de IOL. Al entrar queda una cookie firmada (`httpOnly`) por 30 días; "Salir"
la borra. La contraseña es `SITE_PASSWORD`, en `frontend/.env.local` y en las variables del
proyecto `tp-fintech-web` de Vercel; cambiarla cierra todas las sesiones. En `npm run dev` el
login está apagado.

La API se llama solo desde el servidor de Next.js (server components y server actions), así
que `API_KEY` nunca llega al navegador. Comprar, vender y mantener usan azul, naranja y gris
(validados para daltonismo) y siempre van con la palabra y un símbolo.

## IOL Inversiones

El cliente (`backend/app/brokers/iol.py`) usa la API de https://developers.iolinversiones.com
(`https://api.iolinversiones.com`), con el mismo usuario y contraseña de IOL. Lo que usa la app:

| Para qué | Endpoint |
| --- | --- |
| Cartera | `GET /broker/accounts/AR/positions` |
| Saldos | `GET /broker/accounts/AR/balances` |
| Valor de la cuenta día por día, en pesos y dólar MEP | `GET /broker/accounts/AR/portfolio/history` |
| Cotizaciones (BYMA, NYSE, NASDAQ) | `GET /broker/market-data/{símbolo}/quote` |
| Velas diarias | `GET /broker/market-data/{símbolo}/bars` |
| Panel Merval | `GET /broker/market-data/screener?panel=argaccionesmerval` |
| Costos reales de una orden | `POST /broker/orders/estimate` |
| Órdenes reales (solo con `IOL_LIVE_TRADING=true`) | `POST /broker/orders`, `DELETE /broker/orders/{id}` |

Detalles que maneja el cliente: cada acción de EE.UU. está en un solo mercado (AAPL en NASDAQ,
XOM en NYSE), así que se prueba uno y otro; los bonos cotizan cada 100 nominales; y si IOL no
responde (pasa de noche) se usan los datos guardados.

## API desplegada (Vercel)

La API corre en Vercel como función serverless: **https://tp-fintech-api.vercel.app**
(proyecto `tp-fintech-api`, raíz `backend/`).

- Todas las rutas salvo `/health` piden el header `X-API-Key` con el valor de `API_KEY`. El
  frontend lo manda desde el servidor de Next.js; nunca va al navegador.
- `/docs` y `/openapi.json` están apagados en producción (siguen andando en local).
- Variables de entorno en Vercel: las mismas cinco claves de los Secrets de GitHub, más
  `API_KEY`, `IOL_LIVE_TRADING` y `TAGGER_MODEL`.
- Como cada request puede caer en una instancia nueva, lo que antes vivía en memoria está en
  Supabase: velas diarias (`daily_bars`), snapshots de la cartera (`holdings_snapshots`) y la
  sesión de IOL (`iol_session`, para no loguearse con la contraseña en cada arranque).

Para redesplegar a mano: `cd backend && npx vercel deploy --prod`.

## Tareas programadas (Supabase pg_cron)

Los jobs los dispara `pg_cron` adentro de Supabase, que llama a la API en Vercel con `pg_net`
(migración `supabase/migrations/20261023010000_pg_cron_jobs.sql`). Primero se usó el cron de
GitHub Actions, pero en la práctica corría cada ~5 horas en vez de cada 10 minutos.

| Job | Cuándo (hora Argentina) | Endpoint | Qué hace |
| --- | --- | --- | --- |
| `collect` | cada 10 minutos | `POST /jobs/run` | cartera, mercados y noticias, etiquetado con Gemini, recomendaciones live |
| `trades` | cada 5 minutos, lunes a viernes de 11 a 17 | `POST /jobs/trades` | llena compras en cola y revisa stop loss / take profit |
| `after-close` | 17:30, lunes a viernes | `POST /jobs/after-close` | baja dividendos y cupones, califica las recomendaciones del día y emite las del día siguiente |

La API key que usan está en Supabase Vault (`api_key`); se carga o actualiza con
`cd backend && uv run python -m scripts.set_cron_secret`. Los workflows de `.github/workflows/`
quedan solo para correr un job a mano (pestaña Actions > *Run workflow*), o localmente
`cd backend && uv run python -m scripts.run_job {cycle|trades|after-close}`.

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

Cada ciclo calcula un puntaje entre -1 y +1 por ticker (`backend/app/analysis/scoring.py`). La
página `/como-decide` lo explica con un ejemplo real del día, y `GET /model` devuelve los pesos y
umbrales vigentes.

| Señal | Qué mide | Peso |
| --- | --- | --- |
| Noticias y mercados de predicción | noticias de las últimas 36 h (pierden la mitad del peso cada 12 h) y el movimiento en 24 h de los mercados de predicción, contando cada evento y cada noticia repetida en varios medios una sola vez | 65% |
| Tendencia | precio contra su promedio de 20 días | 5% |
| Contexto | tendencia de todo el mercado: líderes del Merval, bonos o S&P 500 | 10% |
| Brecha del CEDEAR | si el CEDEAR está caro o barato frente a la acción en EE.UU., descontando el dólar | 10% |
| Riesgo país y dólar | cambio de 5 días del riesgo país (bonos y bancos; mitad para las demás acciones locales) o del dólar CCL (CEDEARs), comparado con lo normal del último año. Datos de argentinadatos.com | 10% |

**Ya está en el precio**: cada noticia o mercado se descuenta según cuánto se movió el precio en
su dirección desde que apareció, medido en "días típicos" de esa acción; después de 1,5 días
típicos deja de contar. Una noticia publicada durante la rueda se compara contra el cierre del
día anterior, así no queda "sin descontar" un movimiento que ya pasó ese mismo día.

**Lo que no cuenta, o cuenta menos**: las notas de cierre ("así cerró el mercado", "las acciones
subieron hasta 6%") se ignoran porque solo cuentan lo que ya pasó. Una noticia etiquetada para un
ticker, para todo el Merval o para otra empresa del sector cuenta una sola vez, con el peso de la
etiqueta más directa. Las noticias generales del Merval o de los bonos cuentan 50%; las de otra
empresa del mismo sector (bancos, petróleo y gas, electricidad, materiales, tecnología) cuentan
30%, y todas juntas suman como máximo 0,25. Los adelantos de algo cuyo resultado no se conoce
("se vienen los balances", "qué mirar esta semana") tampoco cuentan. Los mercados de predicción que resuelven en más de 6 meses pesan menos.

**Concentración**: si ya tenés más de 60% de la cartera en el mismo riesgo (riesgo argentino:
acciones locales, bonos y VIST; o activos del exterior), las compras de ese grupo pierden 2 puntos
de puntaje por cada punto arriba del 60% (como máximo 0,3), y la recomendación lo explica. Como
hay solo dos grupos, uno siempre está en 50% o más, por eso el límite está arriba de eso.

Los tickers en cartera solo pueden recibir vender (desde -0,45) o mantener; el resto, comprar
(desde +0,3) o mantener. Vender pide una señal más fuerte porque implica pagar comisiones y
desarmar una posición. Junto a cada recomendación se muestra cuánto cambió el precio en 3 meses y
qué tan lejos está de su máximo.

**Dividendos y cupones**: el calendario de ex-dividendos de Nasdaq (gratis, sin key) cubre las
acciones de EE.UU. de los CEDEARs y los ADRs de las empresas argentinas; los Bonares y Globales
pagan el 9 de enero y el 9 de julio. Se guardan en `corporate_events` después de cada cierre. No
son una señal: cada recomendación avisa "el 9/1 corta cupón" y, al medir resultados, el
dividendo se suma al rendimiento cierre a cierre de ese día.

**Porcentaje de acierto**: con 20 o más recomendaciones calificadas de la misma acción y un
puntaje parecido (`GET /track-record/calibration`), en vez de "señal fuerte" se muestra "con
puntajes así acertó 58% de las veces".

**Cuánto comprar** (`GET /tickers/{t}/plan`): la menor de cinco cantidades, y el panel dice cuál
manda. Arriesgar 1% de la cartera hasta el stop loss (2 ATR), el efectivo disponible, que el
ticker no pase el 10% de la cartera, que su grupo de riesgo no pase el 60% (si ya lo pasó, como
mucho 2% más), y no más del 10% del volumen diario promedio.

A las 17:30 se califican las recomendaciones del día y se emiten las del día siguiente. Como una
recomendación hecha después del cierre recién se puede ejecutar a la apertura, se mide de
**apertura a cierre** del día siguiente (también se guarda cierre a cierre). Comprar acierta si
sube, vender si baja; mantener algo que tenés acierta si no cae más de 1,5%.

- `GET /track-record/simulation`: cuánto valdría la cartera siguiendo el plan de cada día (el mismo
  código que "Tu plan de hoy": ventas, compras pagadas con efectivo o rotando, a la apertura, con
  los costos reales de IOL),
  comparado con lo que hiciste, con quedarte quieto con la cartera del primer día y con comprar
  las 20 líderes del Merval en partes iguales (IOL no publica el índice).
- `GET /track-record/signals`: cuántas veces acertó cada señal por separado.

### Plan del día y rotación

`GET /portfolio/plan` (`backend/app/analysis/rotation.py`) convierte las recomendaciones en un plan
para toda la cartera, con la plata que hay: primero se venden las posiciones que dicen vender;
después cada compra, de mejor a peor puntaje y del tamaño del panel de compra, se paga con el
efectivo. Si no alcanza, propone rotar: vender parte de una posición que la compra supera por
0,35 o más de puntaje y que no se espera que suba (puntaje hasta 0,1), primero las que están fuera
del perfil. Lo que no se puede pagar se informa en vez de recomendarse igual. Las operaciones de
menos del 1% de la cartera quedan afuera.

### Perfil de inversor (CNV)

Cada activo tiene un riesgo (`backend/app/analysis/suitability.py`): **bajo** para bonos y ONs que
se mueven hasta 12% al año; **medio** para el resto de los bonos y para acciones, CEDEARs y ETFs que
se mueven hasta 30% al año; **alto** para lo que se mueve más o no tiene historial. Conservador
llega hasta bajo, moderado hasta medio, arriesgado a todo. Lo que está por encima del perfil nunca
sale como "comprar" (queda en mantener, con la razón) y comprarlo igual pide una confirmación
explícita, también en la API (`accept_out_of_profile`). El perfil también fija el riesgo por compra
(0,5%, 1% o 1,5% de la cartera) y el máximo por activo (5%, 10% o 15%).

El perfil sale del test del inversor de IOL (la API nueva no lo expone, se lee de la anterior,
`/api/v2/datos-perfil`, una vez por día); mientras IOL no lo tenga se usa el que el usuario elige
en `/perfil`, y sin ninguno, conservador.

### Alertas por mail

`backend/app/alerts.py` manda un mail (con [Resend](https://resend.com), gratis) cuando algo que
tenés pasa a "vender", cuando falla un paso de un job y cuando se agota la cuota gratis de
Gemini. Cada alerta sale una sola vez (`alerts_sent`). Necesita `RESEND_API_KEY` y
`ALERT_EMAIL` en el backend; sin ellas solo se registra en el log. El remitente de prueba de
Resend solo entrega al mail con el que se creó la cuenta.

### Tests

```bash
cd backend && uv run pytest
```

Prueban las partes puras del cálculo: el filtro de notas de cierre, "ya está en el precio",
contar una vez, el contagio por sector, la concentración, los umbrales, la señal de riesgo país y
dólar, el tamaño de la compra y la calificación con dividendos y cupones.

### Validación

- `uv run python -m scripts.backtest_trend 180`: la tendencia, probada en 6 meses de 40 tickers
  (3.936 días), acertó la dirección del día siguiente el 49,0% de las veces (correlación +0,003),
  o sea nada. Por eso pesa 5%.
- `uv run python -m scripts.fit_weights`: cuando haya al menos 300 recomendaciones calificadas en
  8 días, ajusta los pesos con una regresión logística entrenada con los días viejos y probada
  con los recientes. No cambia nada solo; sugiere.

## Paper trading

IOL no ofrece un sandbox utilizable, así que con `IOL_LIVE_TRADING=false` (el valor por
defecto) las compras se simulan: se registran en `trade_intents` y se ejecutan en el momento al
último precio de IOL, también con el mercado cerrado (en ese caso, el último cierre). Si IOL no
responde, se usa el último cierre guardado. Con el mercado abierto, un job revisa cada 5 minutos
el stop loss y el take profit.
