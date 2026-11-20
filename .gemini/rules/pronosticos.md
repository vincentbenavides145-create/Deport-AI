---
description: Reglas Oficiales de Pronósticos Deportivos (DEPORT AI)
globs: *
---

# Reglas Oficiales de Pronósticos Deportivos (DEPORT AI)

Cuando el usuario pida analizar un partido, pronósticos o predicciones de fútbol (por ejemplo: "Analiza Real Madrid vs Barcelona", "ac milan vs venezia fc", "analiza alianza atletico vs comerciantes unidos", "¿Quién gana hoy?"):

## ⛔ PROHIBICIONES ESTRICTAS (BAJO NINGUNA CIRCUNSTANCIA INCLUIR):
1. **PROHIBIDO mostrar probabilidades menores al 60.0% (< 60.0%):** En NINGUNA categoría (goles, córners, tarjetas, remates, jugadores, mitades, fueras de juego, etc.) se pueden incluir selecciones que no alcancen el 60.0%. La única excepción es el marcador exacto más probable dentro de las proyecciones numéricas.
2. **PROHIBIDO incluir apuestas de Hándicap:** Quedan eliminadas y prohibidas todas las apuestas de Hándicap (Asiático o Europeo).
3. **PROHIBIDO incluir líneas triviales o fuera del MarketPresentationCatalog:** No mostrar bajo ningún concepto líneas triviales (ej: Más de 0.5 goles, Más de 3.5 córners totales, Más de 1.5 córners por equipo, Más de 0.5 tarjetas por equipo, Más de 1.5 tarjetas totales, Más de 0.5 fueras de juego, Más de 7.5 remates), aunque superen el 90% o 99%.
4. **REGLA DE LA LÍNEA MÁS EXIGENTE (NO la más probable):** Dentro de cada mercado permitido, DEPORT AI escoge la línea válida MÁS EXIGENTE que conserve probabilidad ≥ 60.0% (ej: +8.5 córners al 66% antes que +7.5 al 85%).
5. **PROHIBIDO incluir múltiples apuestas del mismo tipo:** Solo debe incluirse una única selección por cada concepto o subtipo (ej: en goles totales solo una línea, en doble oportunidad solo una, para un mismo jugador solo su mejor prop).
6. **LÍMITE de máximo 4 apuestas por categoría:** Cada categoría puede contener como máximo 4 selecciones, presentadas estrictamente en orden de mayor a menor probabilidad.
7. **PROHIBIDO generar tablas:** No crees tablas markdown de goles, cuotas, edges ni comparativas de mercado.
8. **PROHIBIDO incluir "Mercados a Evitar" o "Trampas":** No generes ninguna sección ni viñeta de mercados a evitar, advertencias de valor negativo o trampas.
9. **PROHIBIDO mostrar variables matemáticas internas:** No menciones `shared_goal_component`, `W`, parámetros de interdependencia ni coeficientes crudos del modelo.
10. **PROHIBIDO incluir la Auditoría en Cascada (Waterfall Attribution):** No muestres desglose de Base Liga, Ventaja Local, Impacto Elo, etc.
11. **PROHIBIDO usar etiquetas de niveles:** No uses "(Nivel Oro)", "(Nivel Plata)" ni "(Banker)".
12. **PROHIBIDO generar muros de texto:** Cada selección debe llevar una justificación concisa de **exactamente una sola línea**, comenzando con `  *Porque ...*`.
13. **PROHIBIDO forzar categorías vacías (ESTRUCTURA ADAPTATIVA):** Si en una categoría no hay selecciones válidas del catálogo que alcancen el 60.0%, **NO muestres ese encabezado**. La respuesta debe fluir únicamente con los mercados donde el partido realmente ofrezca solidez estadística.

## 💰 CUOTAS Y VALOR ESPERADO (cuando el plan de Sportmonks incluye cuotas)
- Si una selección tiene cuota, el comando calcula su valor esperado: **EV = probabilidad × cuota − 1**.
- Las selecciones con cuota y EV menor a +3% **se descartan aunque superen el 60%** (la cuota no paga el riesgo).
- Dentro de cada mercado con cuotas se elige la selección de **mayor EV** (no la más probable), y el Pick Recomendado es la de mayor EV.
- La línea se muestra como: `• **<Selección> — XX.X%** · cuota X.XX · EV +X.X%`. Sin cuotas, el formato no cambia.

## 📒 HISTÓRICO DE PREDICCIONES (OBLIGATORIO)
- `analyze.py` registra automáticamente cada predicción y además la escribe en `history/predictions.jsonl`, dentro del repositorio. Es el histórico permanente: las sesiones en la nube son temporales y la base SQLite local se pierde al cerrarlas (se reconstruye sola desde ese archivo).
- No uses `--no-track` salvo para pruebas.
- **Después de cada análisis**, sube el histórico: `python track.py sync` (commit y push a `main`).
- Para comprobar con los resultados reales: `python track.py update` (liquida con Sportmonks), `python track.py report` y `python track.py sync`.
- Al empezar una sesión nueva, ejecuta primero `python track.py update` y `python track.py sync` para liquidar lo pendiente.

## 🧪 CALIBRACIÓN Y PARÁMETROS
- La calibración dinámica solo se activa con **30 o más predicciones reales liquidadas** por categoría. Nunca se inventan datos para calibrar.
- Los parámetros del modelo por liga se ajustan con `python backtest.py --teams-file <liga.txt> --fit --save-params` y se guardan en `model_params.json`.

## ⚡ MANEJO DE PARTIDOS EN VIVO
Si un equipo está jugando un partido en directo en este momento, el motor calcula el análisis con todos los partidos finalizados previos, excluyendo de forma automática los datos incompletos del partido en vivo.

---

## 🎯 FLUJO DE EJECUCIÓN OBLIGATORIO

1. Ejecuta el script oficial en la terminal:
   ```powershell
   python analyze.py "<Equipo 1> vs <Equipo 2>" --report
   ```
2. El script ejecuta el motor de cálculo, aplica estrictamente el `MarketPresentationCatalog` (descartando líneas triviales y eligiendo la línea más exigente ≥ 60.0%) y genera DIRECTAMENTE el reporte oficial adaptativo en formato Markdown.
3. **MUESTRA DIRECTAMENTE AL USUARIO EL REPORTE ADAPTATIVO OBTENIDO DEL COMANDO.**
   ⛔ **ESTÁ ESTRICTAMENTE PROHIBIDO:**
   - No intentes deducir, inventar ni recalcular líneas a mano a partir de estadísticas crudas (NUNCA inventar Más de 0.5 goles, Más de 3.5 córners, Más de 1.5 córners ni Más de 0.5 tarjetas).
   - No muestres selecciones que no hayan sido validadas y devueltas por el comando oficial.

---

### Estructura Dinámica Generada por el Comando:

# ⚽ <Equipo 1> vs <Equipo 2>
**Confianza:** <🟢 Alta / 🟡 Media / 🔴 Baja> (<Detalle breve: muestra de partidos, confirmación de alineación>)

*(Despliega ÚNICAMENTE los bloques temáticos donde existan selecciones ≥ 60.0%):*

#### 🏆 Resultado *(si hay 1X2, Doble Oportunidad o DNB ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación táctica/estadística en 1 sola línea>.*

#### 🥅 Goles y Anotaciones *(si hay Goles Totales, Ambos Marcan o Goles de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### ⏱️ Mercados por Mitad *(si hay 1T o 2T ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🚩 Córners *(si hay Córners Totales o de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🟨 Tarjetas *(si hay Tarjetas Totales o de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🎯 Remates y Tiros al Arco *(si hay Remates Totales, al Arco o de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🚩 Fueras de Juego (Offsides) *(si hay Offsides Totales o de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 💥 Especiales del Partido *(si hay Tiros al Poste / Woodwork ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 👟 Jugadores *(si hay Remates, Tiros al Arco o Goleadores de jugadores ≥ 60%)*
• **<Nombre Jugador> <Línea de remates/tiros al arco con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*  
  *(Requiere confirmar titularidad oficial)*.

#### 📊 Proyecciones numéricas *(cierre de referencia matemática)*
• **Goles estimados:** X.XX (<Equipo 1>: X.XX | <Equipo 2>: X.XX)  
• **Córners estimados:** X.XX  
• **Tarjetas estimadas:** X.XX  
• **Remates estimados:** XX.X  
• **Marcador más probable:** X - X (XX.X%)
