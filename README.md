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
  la ventana consultada.
- **1X2, over/under y ambos marcan:** agregaciones de la matriz de marcadores.
- **Córners y tiros:** producción del equipo combinada con concesión del rival,
  usando estimación robusta para limitar partidos extremos.
- **Jugadores:** tasa observada por 90 minutos y probabilidad Poisson de registrar
  al menos un tiro al arco.
- **Oportunidades:** solo se considera valor contra cuotas cuando Sportmonks entrega
  precios comparables. Sin cuotas se etiquetan como señales estadísticas.

## Validación del modelo

El módulo `deport_ai.evaluation` permite contrastar predicciones binarias ya
generadas contra resultados conocidos, sin persistir nada: **Brier Score** para
precisión probabilística, **Log Loss** para penalizar exceso de confianza y
grupos de calibración para comparar probabilidad estimada vs. frecuencia real.
Un Brier y un Log Loss menores son mejores; la calibración debe acercarse a la
diagonal. Se recomienda evaluarlo fuera de muestra y por liga/mercado antes de
usar probabilidades como apoyo de decisión.

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
├── service.py          # Orquestación datos → modelos → informe
├── llm.py              # Explicación opcional, nunca cálculo
├── formatter.py        # Formato fijo de salida
└── cli.py              # Chat de terminal
```
