# Tecnología para las Finanzas: portfolio advisor

Combina noticias recientes, mercados de predicción (Polymarket y Kalshi) y la API de
IOL Inversiones (https://developers.iolinversiones.com) para recomendar **comprar / vender / mantener** sobre los tickers del
mercado argentino (acciones, CEDEARs, bonos).

## Flujo

1. **Recolectar** cada 10 minutos: noticias (RSS, GDELT y Google News por empresa), mercados de
   Polymarket y Kalshi, y el cambio de probabilidad de cada mercado (no solo su nivel).
2. **Leer**: Gemini Flash-Lite (free tier, temperatura 0) responde una sola pregunta por noticia (de
   qué activo habla, y si es bueno, malo o incierto) y por mercado (qué empuja su SÍ).
3. **Controlar** con reglas lo que respondió: el activo tiene que estar nombrado en el texto, y una
   apuesta sobre el precio de una acción se descarta.
4. **Puntuar**: promedio ponderado de lo que se sabe de cada activo, entre -1 y +1.
5. **Rankear** dentro de cada clase (acciones, CEDEARs, bonos): solo se compra el 20% mejor.
6. **Antes de abrir** (10:15) sale la recomendación del día: la que se ve, se sigue y se mide.
7. **Medir** después del cierre contra la mediana de su clase, con una cartera simulada continua y
   las pruebas de los papers (costos, placebos, atraso).

## Funcionalidades

- **Track record**: se guarda cada recomendación con la versión del modelo que la hizo, y se compara
  contra la mediana de su clase. Acierto por señal.
- **SL/TP según volatilidad**: distancia en base al ATR de cada ticker, y tamaño de la
  posición para que un stop-out pierda un % fijo del portfolio.
- **CEDEAR, acción o dólar**: para cada CEDEAR se separa cuánto del movimiento es la acción y
  cuánto es el dólar, en una frase simple. El dólar es el mismo para todos ese día: la mediana de
  lo que se movieron en pesos menos lo que se movió su acción afuera, en una canasta de nueve.
- **Caución para la plata parada**: lo que queda después del plan del día, si llega al mínimo de
  IOL, se sugiere en caución al plazo más corto, con la tasa y los costos reales. No la ejecuta.
- **Cobertura con opciones**: para un ticker en cartera con señal fuerte de venta, sugerir un
  put protectivo de la cadena de opciones.
- **Alertas de apuestas grandes**: trades grandes recientes en Polymarket sobre mercados que
  afectan a los tickers del usuario.
- **Polymarket vs Kalshi**: cuando ambos listan el mismo evento con probabilidades distintas,
  se muestran los dos (medida de incertidumbre).
- **Mercados argentinos**: filtro de mercados sobre elecciones, FMI, inflación y Fed,
  mapeados a Merval, bonos y ADRs.
- **Horario de mercado**: BYMA abre a las 10:30 (ART), y acciones y CEDEARs operan hasta las 18:00
  (bonos y cauciones, hasta las 17:00), salvo feriados. Fuera de horario las
  compras quedan en cola y se muestra una vista previa del día siguiente.
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
| `/` Hoy | qué comprar (con la razón principal), el plan del día, las últimas noticias y lo que esperan los mercados de predicción |
| `/cartera` | valor, qué vender, posiciones con su PPC y el detalle de sus operaciones, y valor en el tiempo |
| `/ticker/[símbolo]` | recomendación, por qué, compra en un click con stop loss y take profit, y precio de 3 meses |
| `/operaciones` | las operaciones reales de IOL con su resultado, y las simuladas desde el sitio |
| `/historial` | cuántas recomendaciones acertaron y el detalle día por día |

Arriba de todo hay una cinta con las recomendaciones del día.

El sitio está en **https://tp-fintech-web.vercel.app** y pide contraseña en `/login`, porque
muestra la cartera real de IOL. Al entrar queda una cookie firmada (`httpOnly`) por 30 días; "Salir"
la borra. La contraseña es `SITE_PASSWORD`, en `frontend/.env.local` y en las variables del
proyecto `tp-fintech-web` de Vercel; cambiarla cierra todas las sesiones. En `npm run dev` el
login está apagado.

La API se llama solo desde el servidor de Next.js (server components y server actions), así
que `API_KEY` nunca llega al navegador. Comprar, vender y mantener usan verde, rojo y gris, y
siempre van con la palabra y un símbolo, así que el color nunca es la única señal.

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
| `collect` | cada 10 minutos | `POST /jobs/run` | cartera, mercados y noticias, etiquetado con Gemini, y entre sesiones una vista previa del día siguiente |
| `before-open` | 10:15, días de mercado | `POST /jobs/before-open` | lo último de noticias y mercados, y las recomendaciones del día: las que se ven y las que se miden |
| `trades` | cada 5 minutos, mientras BYMA está abierto | `POST /jobs/trades` | llena compras en cola y revisa stop loss / take profit |
| `after-close` | 18:30, lunes a viernes | `POST /jobs/after-close` | baja dividendos y cupones, califica las recomendaciones del día y recalcula la simulación y las pruebas |

La API key que usan está en Supabase Vault (`api_key`); se carga o actualiza con
`cd backend && uv run python -m scripts.set_cron_secret`. Los workflows de `.github/workflows/`
quedan solo para correr un job a mano (pestaña Actions > *Run workflow*), o localmente
`cd backend && uv run python -m scripts.run_job {cycle|before-open|trades|after-close}`.

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

La página `/como-decide` explica todo esto con un ejemplo real del día, y `GET /model` devuelve las
constantes y los prompts vigentes.

### El modelo (versión 2)

**Gemini lee, no decide** (`backend/app/analysis/tagger.py`). Hay dos prompts, uno por tipo:

- **Noticia**: los activos de los que habla explícitamente, y si es bueno, malo o incierto para su
  precio en 1 a 3 días. "Incierto" es una respuesta válida. Si no nombra a ninguno, lista vacía.
- **Mercado de predicción**: qué significa el SÍ, y qué empuja: un activo, solo si lo nombra, o un
  factor (`backend/app/analysis/factors.py`: petróleo, oro, bitcoin, bolsa de EE.UU., tecnología e
  IA, tasas de EE.UU., riesgo argentino). Una tabla fija dice a quién llega cada factor.

**Controles que no dependen de Gemini**: el activo tiene que estar nombrado en el texto con palabras
que sean de ese activo; una apuesta sobre el precio de una acción o un índice se descarta, porque
solo repite el precio; en una apuesta sobre el petróleo, el oro o bitcoin la dirección sale del
título; un rango queda como incierto.

**El puntaje** (`backend/app/analysis/scoring.py`) es un solo cálculo:

```
puntaje = suma(peso × valor) / (suma(pesos) + 1)
```

| Evidencia | Valor | Peso |
| --- | --- | --- |
| Noticia | +1, -1 o 0 si es incierta | 1 hasta que una apertura pudo operarla, la mitad después de una, nada después de dos. Noches, fines de semana y feriados no la envejecen |
| Mercado | cambio en 24 h, descontado lo que explica el paso del tiempo, sobre 10 puntos (como mucho 1), con el signo de lo que hace el SÍ | 1 si nombra al activo, 0,5 si llega por un factor. Menos si resuelve a más de 6 meses |

**La decisión**: dentro de cada clase (acciones, CEDEARs, bonos), los activos con evidencia se ordenan
por puntaje, y los iguales comparten el puesto. Comprar: no lo tenés, está en el 20% mejor y tiene
+0,35 o más (un solo mercado por factor no llega). Vender: lo tenés y tiene
-0,6 o menos (una sola mala noticia da -0,5). Lo demás es mantener. Lo que está por encima del perfil
nunca sale comprar.

**Lo que no cuenta**: lo que repite algo publicado en los últimos 7 días sobre el mismo activo
(similitud de palabras de 0,4 o más, mirando solo hacia atrás), las notas de cierre, y los mercados con
menos de US$ 1.000 operados en el día, con un movimiento de menos de 2 puntos o a menos de 3 días de
resolverse. Varios mercados de un evento cuentan una vez: el más operado.

**Riesgo país y dólar CCL** se miden al lado del puntaje, pero no entran. Se sumarán si con más
historia siguen funcionando.

**Dividendos y cupones**: el calendario de ex-dividendos de Nasdaq (gratis, sin key) cubre las
acciones de EE.UU. de los CEDEARs y los ADRs de las empresas argentinas; los Bonares y Globales
pagan el 9 de enero y el 9 de julio. Se guardan en `corporate_events` después de cada cierre. No
son una señal: cada recomendación avisa "el 9/1 corta cupón" y, al medir resultados, el
dividendo se suma al rendimiento cierre a cierre de ese día.

**Cuánto comprar** (`GET /tickers/{t}/plan`): la menor de cinco cantidades, y el panel dice cuál
manda. Arriesgar 1% de la cartera hasta el stop loss (2 ATR), el efectivo disponible, que el
ticker no pase el 10% de la cartera, que su grupo de riesgo no pase el 60% (si ya lo pasó, como
mucho 2% más), y no más del 10% del volumen diario promedio. La confianza del modelo no interviene.

### Cómo se mide

Las recomendaciones salen a las 10:15 y se miden de **apertura a cierre** de ese día, contra la
**mediana de su clase**. Comprar acierta si le gana, vender si pierde contra ella. Mantener no es una
apuesta. Cada fila guarda `model_version`, para no mezclar modelos.

- `GET /track-record/simulation`: cuánto valdría la cartera siguiendo el plan de cada día: una cartera
  propia que se arrastra de un día a otro desde la real del primer día (el mismo código que "Tu plan
  de hoy": ventas, compras pagadas con efectivo o rotando, a la apertura, con los costos reales de
  IOL). Cada compra del plan lleva su stop loss y take profit, que se disparan con el máximo y el
  mínimo de cada día; si los dos entran en la misma vela, cuenta el stop,
  comparado con lo que hiciste, con quedarte quieto con la cartera del primer día y con comprar
  las 20 líderes del Merval en partes iguales (IOL no publica el índice). Con retorno, caída máxima y
  Sortino.
- `GET /track-record/evaluation` (`backend/app/analysis/evaluation.py`): si el ranking dice algo. El
  mejor 20% contra el peor 20% a 1, 2 y 3 días, con costos de 5, 10 y 20 pb, la reacción a la apertura
  (que no se puede operar), placebos, signos invertidos y atraso. Antes de 20 ruedas la página avisa
  que no alcanza para concluir.
- `GET /track-record/signals`: cuántas veces acertó cada señal por separado.

### Pasar al modelo 2

En este orden. La migración funciona con el código anterior, así que no hay corte:

```bash
cd backend && uv run python scripts/migrate.py
```

Después, desplegar y correr:

```bash
cd backend && uv run python -m scripts.start_model_v2
```

Vuelve a pedir a IOL las velas guardadas antes de que su día cerrara, marca para etiquetar de nuevo lo
de los últimos 5 días (las etiquetas viejas quedan, como del primer modelo) y vuelve a calificar todo
contra la mediana de su clase.

### Universo de activos

`backend/app/universe.py` trae de los paneles de IOL, una vez por día, todas las acciones, CEDEARs
(los ETFs vienen adentro) y bonos en pesos con precio: unos 590. Gemini puede etiquetar cualquiera.
Por tiempo, cada ciclo puntúa como máximo 100: primero la cartera, después los que tienen las
noticias y mercados más fuertes. Las obligaciones negociables y las letras no se incluyen.

### Control contra IOL

`backend/app/reconcile.py` compara cada día hábil el valor del sitio al cierre con el que publica
IOL. Si difieren más de 0,3%, manda un mail.

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

El perfil se define en el código (`INVESTOR_PROFILE` en `suitability.py`): hoy, moderado. IOL no lo
expone en su API y la app tiene un solo usuario.

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

Prueban las partes puras del cálculo: los controles sobre las respuestas de Gemini, la novedad, las
aperturas y feriados, el promedio, el ranking, los mercados y sus factores, la cartera simulada, el
tamaño de la compra, la calificación contra la clase y las pruebas de la señal.

### Validación

`uv run python -m scripts.tagger_check 40` prueba a Gemini sobre noticias ya recolectadas, sin guardar
nada: la misma noticia dos veces (estabilidad) y con el nombre de la empresa tapado, como Glasserman
y Lin (si la dirección cambia). Gasta cuota del free tier.

## Paper trading

IOL no ofrece un sandbox utilizable, así que con `IOL_LIVE_TRADING=false` (el valor por
defecto) las compras se simulan: se registran en `trade_intents` y se ejecutan en el momento al
último precio de IOL, también con el mercado cerrado (en ese caso, el último cierre). Si IOL no
responde, se usa el último cierre guardado. Con el mercado abierto, un job revisa cada 5 minutos
el stop loss y el take profit.
