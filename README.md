# DEPORT AI

Asistente conversacional de fútbol para terminal, alimentado exclusivamente por
Sportmonks Football API v3. No crea una página web, usuarios, autenticación propia,
base de datos ni historial persistente.

```text
Sportmonks (datos reales)
          ↓
Poisson bivariado + Dixon-Coles + Elo dinámico + modelos de conteo
          ↓
Probabilidades cerradas y trazables
          ↓
LLM opcional: únicamente explica, no calcula ni cambia cifras
```

## Datos consultados

- Identificación de equipos mediante búsqueda de Sportmonks.
- Fixtures por rango de fechas y próximo enfrentamiento.
- Historial H2H.
- Forma reciente, rendimiento local y visitante.
- Goles, tiros, tiros al arco, córners, posesión y tarjetas.
- Estadísticas por jugador y probabilidad de tiro al arco.
- Alineaciones, formaciones y bajas cuando están publicadas.
- Cuotas únicamente si el plan contratado las incluye. El token actualmente conectado
  no tiene habilitado el módulo de odds, por lo que se muestra como no disponible.

Los campos ausentes nunca se rellenan con cifras generadas por el LLM.

## Instalación en Windows

Requiere Python 3.11 o superior y un token de Sportmonks.

```powershell
cd "C:\Users\vince\OneDrive\Documentos\PRONOSTICOS FUTBOL"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
notepad .env
```

Configuración mínima:

```dotenv
SPORTMONKS_API_TOKEN=tu_token
SPORTMONKS_BASE_URL=https://api.sportmonks.com/v3/football
```

La capa LLM es opcional:

```dotenv
OPENAI_API_KEY=tu_clave_openai
OPENAI_MODEL=gpt-5.2
```

Sin `OPENAI_API_KEY`, todos los cálculos funcionan y se utiliza una explicación
determinista. La aplicación no escribe prompts, respuestas ni datos deportivos en
disco. Su caché existe únicamente durante la ejecución.

## Ejecutar

```powershell
python -m deport_ai
```

Ejemplos:

```text
Tú > Analiza Real Madrid vs Barcelona
Tú > Alianza Lima contra Sporting Cristal
Tú > salir
```

### Uso desde Gemini Antigravity

Gemini puede solicitar un análisis estructurado ejecutando:

```powershell
python analyze.py "Real Madrid vs Barcelona" --json
```

`analyze.py` consulta Sportmonks, ejecuta los modelos estadísticos y devuelve
JSON. Gemini debe limitarse a interpretar esas cifras: no debe recalcularlas,
alterarlas ni completar campos ausentes.

## Modelos

- **Goles:** medias recientes ponderadas por recencia, sede y fuerza Elo. Si el
  proveedor publica xG con muestra suficiente, se incorpora como señal parcial,
  sin sustituir los goles reales.
- **Poisson bivariado:** matriz conjunta de marcadores 0–0 a 10–10. Incluye un
  componente compartido, estimado solo desde los partidos recientes, para no
  asumir que los goles de ambos equipos son independientes.
- **Dixon-Coles:** corrección para 0–0, 0–1, 1–0 y 1–1 sobre esa matriz conjunta.
- **Elo dinámico:** ventaja local y resultados recientes con mayor peso dentro de
  la ventana consultada. El prior inicial usa la tabla de niveles de club escalada
  por `club_tier_scale`; ya no suma un bonus por diferencia de goles (esos partidos
  ya entran en la forma reciente).
- **Sin doble conteo:** el factor Elo se aplica con un peso `elo_weight` (0–1)
  ajustado con datos, porque Elo y forma reciente salen de los mismos partidos. El
  ajuste por nivel del rival (SoS) queda desactivado por defecto por el mismo motivo.
- **Parámetros por liga (`model_params.json`):** rho de Dixon-Coles, peso Elo, peso
  sede/global, peso temporada, escala de la tabla de clubes y dispersión de córners
  y tarjetas. Sin archivo se usan valores por defecto conservadores.
- **1X2, over/under y ambos marcan:** agregaciones de la matriz de marcadores.
- **Córners y tiros:** producción del equipo combinada con concesión del rival,
  usando estimación robusta para limitar partidos extremos.
- **Jugadores:** tasa observada por 90 minutos y probabilidad Poisson de registrar
  al menos un tiro al arco.
- **Cuotas y valor:** si Sportmonks entrega cuotas, cada selección con precio lleva
  `EV = probabilidad × cuota − 1`; las de EV < +3 % se descartan aunque sean muy
  probables, y dentro de cada mercado se elige la de mayor EV. Sin cuotas se
  muestran como señales estadísticas.

## Validación del modelo

`backtest.py` ejecuta un backtest **walk-forward** (cada partido se predice solo con
partidos anteriores) de **todos** los mercados, no solo goles:

```powershell
# Verificar el pipeline sin token (liga simulada)
python backtest.py --synthetic

# Backtest real: pasar TODOS los equipos de una liga (uno por línea)
python backtest.py --teams-file laliga.txt --count 40 --output informe.md

# Ajustar parámetros por máxima verosimilitud y guardarlos para la liga
python backtest.py --teams-file laliga.txt --count 40 --fit --save-params

# Medir ROI con cuotas históricas (si el plan las incluye)
python backtest.py --teams-file laliga.txt --with-odds

# Alimentar la calibración dinámica con resultados walk-forward reales
python backtest.py --teams-file laliga.txt --save-calibration
```

El informe separa:

1. **Lo que ve el usuario** (selecciones 60–88 % tras el filtro): probabilidad media
   mostrada frente al acierto real. Una diferencia negativa indica sobreconfianza
   por sesgo de selección.
2. **Todos los mercados calculados**: calibración global por tramos.
3. **Mercados no liquidables** con los datos disponibles (mitades, córners 1T, DNB con
   empate, jugadores).

Ajustar y evaluar con los mismos partidos es una medición optimista: lo correcto es
ajustar con una temporada y evaluar con la siguiente.

La calibración dinámica (`track.py calibrate`) solo se activa con 30 o más
predicciones **reales** liquidadas por categoría, y aplica la corrección con un peso
de credibilidad `n / (n + 50)`.

## Histórico de predicciones

Cada análisis se registra y se guarda en `history/predictions.jsonl`, dentro del repositorio, para que no se pierda entre sesiones en la nube.

```bash
python track.py update   # liquida las predicciones pendientes con los resultados de Sportmonks
python track.py report   # aciertos, fallos y rentabilidad
python track.py sync     # commit + push del histórico a main
```

## Verificación

```powershell
pytest -q
```

Las pruebas automatizadas no consumen Sportmonks ni OpenAI.

## Estructura

```text
src/deport_ai/
├── sportmonks.py       # Cliente Sportmonks v3 y normalización
├── fixture_contract.py # Contrato interno neutral de fixtures
├── stats_engine.py     # Poisson bivariado, Dixon-Coles, Elo, córners y tiros
├── evaluation.py       # Brier, Log Loss y calibración sin persistencia
├── backtesting.py      # Backtest walk-forward de todos los mercados
├── model_params.py     # Parámetros por liga y ajuste por máxima verosimilitud
├── service.py          # Orquestación datos → modelos → informe
├── llm.py              # Explicación opcional, nunca cálculo
├── formatter.py        # Formato fijo de salida
└── cli.py              # Chat de terminal
```
