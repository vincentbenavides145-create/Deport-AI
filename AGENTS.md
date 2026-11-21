# Reglas Oficiales de Pronósticos Deportivos (DEPORT AI)

Cuando el usuario pida analizar un partido, pronósticos o predicciones de fútbol (por ejemplo: "Analiza Real Madrid vs Barcelona", "ac milan vs venezia fc", "analiza alianza atletico vs comerciantes unidos", "¿Quién gana hoy?"):

## ⛔ PROHIBICIONES ESTRICTAS (BAJO NINGUNA CIRCUNSTANCIA INCLUIR):
1. **PROHIBIDO mostrar probabilidades menores al 75.0% (< 75.0%):** En NINGUNA categoría (goles, córners, tarjetas, remates, jugadores, mitades, fueras de juego, etc.) se pueden incluir selecciones que no alcancen el 75.0%. La única excepción es el marcador exacto más probable dentro de las proyecciones numéricas.
2. **PROHIBIDO incluir apuestas de Hándicap:** Quedan eliminadas y prohibidas todas las apuestas de Hándicap (Asiático o Europeo).
3. **PROHIBIDO incluir líneas triviales o fuera del MarketPresentationCatalog:** No mostrar bajo ningún concepto líneas triviales (ej: Más de 0.5 goles, Más de 3.5 córners totales, Más de 1.5 córners por equipo, Más de 0.5 tarjetas por equipo, Más de 1.5 tarjetas totales, Más de 0.5 fueras de juego, Más de 7.5 remates), aunque superen el 90% o 99%.
4. **REGLA DE MAYOR PROBABILIDAD DENTRO DEL RANGO ÓPTIMO (75.0% - 88.0%):** Dentro de cada mercado permitido, DEPORT AI escoge la selección con MAYOR PROBABILIDAD dentro del rango óptimo de valor deportivo (75.0% a 88.0%). Quedan descartadas las líneas que queden al mínimo del 75% cuando existan líneas más seguras (ej: preferir +1.5 goles al 83.5% antes que +2.5 al 76.9%), y quedan igualmente excluidas las selecciones cercanas al 100% (> 88.0%) por falta de rentabilidad en su cuota.
5. **PROHIBIDO incluir múltiples apuestas del mismo tipo:** Solo debe incluirse una única selección por cada concepto o subtipo (ej: en goles totales solo una línea, en doble oportunidad solo una, para un mismo jugador solo su mejor prop).
6. **LÍMITE de máximo 4 apuestas por categoría:** Cada categoría puede contener como máximo 4 selecciones, presentadas estrictamente en orden de mayor a menor probabilidad.
7. **PROHIBIDO generar tablas:** No crees tablas markdown de goles, cuotas, edges ni comparativas de mercado.
8. **PROHIBIDO incluir "Mercados a Evitar" o "Trampas":** No generes ninguna sección ni viñeta de mercados a evitar, advertencias de valor negativo o trampas.
9. **PROHIBIDO mostrar variables matemáticas internas:** No menciones `shared_goal_component`, `W`, parámetros de interdependencia ni coeficientes crudos del modelo.
10. **PROHIBIDO incluir la Auditoría en Cascada (Waterfall Attribution):** No muestres desglose de Base Liga, Ventaja Local, Impacto Elo, etc.
11. **PROHIBIDO usar etiquetas de niveles:** No uses "(Nivel Oro)", "(Nivel Plata)" ni "(Banker)".
12. **PROHIBIDO generar muros de texto:** Cada selección debe llevar una justificación concisa de **exactamente una sola línea**, comenzando con `  *Porque ...*`.
13. **PROHIBIDO forzar categorías vacías (ESTRUCTURA ADAPTATIVA):** Si en una categoría no hay selecciones válidas del catálogo que alcancen el 75.0%, **NO muestres ese encabezado**. La respuesta debe fluir únicamente con los mercados donde el partido realmente ofrezca solidez estadística.

## 💰 CUOTAS Y VALOR ESPERADO (cuando el plan de Sportmonks incluye cuotas)
- Si una selección tiene cuota, el comando calcula su valor esperado: **EV = probabilidad × cuota − 1**.
- Las selecciones con cuota y EV menor a +3% **se descartan aunque superen el 75%** (la cuota no paga el riesgo).
- Dentro de cada mercado con cuotas se elige la selección de **mayor EV** (no la más probable), y el Pick Recomendado es la de mayor EV.
- La línea se muestra como: `• **<Selección> — XX.X%** · cuota X.XX · EV +X.X%`. Sin cuotas, el formato no cambia.

## 🔎 COHERENCIA ENTRE PROBABILIDAD Y JUSTIFICACIÓN
- Cada justificación cita el historial real (aciertos/partidos y promedio) que el comando usa para validar la selección.
- Se descarta toda selección cuyo historial citado tenga una tasa de acierto menor al 50%, quede más de 20 puntos por debajo de la probabilidad del modelo, o cuyo promedio esté del lado contrario de la línea.
- Los mercados de estadísticas (córners, tarjetas, faltas, remates, offsides, tiros al palo) exigen al menos 6 partidos con esa estadística.
- Mercados correlacionados comparten familia y solo se muestra una selección por familia: {1X2, doble oportunidad, DNB, combinadas de resultado}, {Ambos marcan, valla invicta, gana a cero} y {goles totales, multigoles}.
- El Pick Recomendado no se repite dentro de su categoría.
- Los amistosos internacionales usan un perfil propio (Elo con peso máximo 0.15 y tope de 3.5 / 3.0 goles esperados).
- Las tarjetas se proyectan y liquidan igual: amarillas + rojas (0 si el partido no publica tarjetas).
- Las props de jugador solo se publican con al menos 6 partidos como titular y citan ese historial real ("2+ remates en X de N").
- Un once publicado solo cuenta como confirmado si ambos equipos lo publicaron y faltan 60 minutos o menos para el inicio; antes, las props siguen requiriendo confirmar titularidad.
- Los fueras de juego no se ofrecen si la competición los publica en menos del 80% de los partidos recientes de ambos equipos.
- Las props de jugador y los fueras de juego están suspendidos (no se publican) desde el 20/11/2026: en resultados reales acertaron 50% y 54% con 70%+ prometido. Los mercados por mitad también, desde el 21/11/2026 (61% con 67% prometido).
- El mínimo publicado es 75% desde el 21/11/2026: en resultados reales el acierto siguió a la probabilidad (73% prometido, 73% acertado) y solo desde el 75% se acercaba al 80%.
- La proyección de tarjetas combina a los equipos con el promedio de tarjetas del árbitro asignado (peso hasta 75%, menor si dirigió pocos partidos; validado en 543 partidos de 5 ligas). El reporte lo muestra en «Tarjetas estimadas» con su nombre, promedio y partidos dirigidos.

## 📒 HISTÓRICO DE PREDICCIONES (OBLIGATORIO)
- `analyze.py` registra automáticamente cada predicción y además la escribe en `history/predictions.jsonl`, dentro del repositorio. Es el histórico permanente: las sesiones en la nube son temporales y la base SQLite local se pierde al cerrarlas (se reconstruye sola desde ese archivo, y al reconstruirse recalcula la calibración).
- No uses `--no-track` salvo para pruebas.
- Solo se registran partidos que aún no empiezan. Re-analizar un partido antes del inicio reemplaza sus predicciones pendientes (no se acumulan las de cada análisis).
- **Después de cada análisis**, sube el histórico: `python track.py sync` (commit y push a `main`). Antes de exportar, `sync` trae `main` y fusiona su histórico y su caché de xG: una copia local vieja ya no pisa liquidaciones más recientes, y las predicciones se emparejan por mercado y selección, no por `id`.
- Para comprobar con los resultados reales: `python track.py update` (liquida con Sportmonks), `python track.py report` y `python track.py sync`.
- Al empezar una sesión nueva, ejecuta primero `python track.py update` y `python track.py sync` para liquidar lo pendiente.

## 🧪 CALIBRACIÓN Y PARÁMETROS
- La calibración dinámica solo se activa con **30 o más predicciones reales liquidadas** (ganadas o perdidas; las anuladas no cuentan) por categoría. Nunca se inventan datos para calibrar.
- La calibración se hace también por lado (Más/Menos) dentro de cada categoría, y lo que una liga aún no tiene se toma de la calibración global. Los «Menos de» de córners, tarjetas, tiros al arco, remates y faltas solo se publican cuando ese lado tiene su propia calibración (30+ liquidadas): en resultados reales acertaron 58-64% con 71-75% prometido.
- La corrección de sesgo de córners y tarjetas solo usa la proyección del **total del partido** (una vez por partido, 30+ partidos). Los goles esperados no se corrigen después de calcular la matriz de marcadores.
- Las combinadas (doble oportunidad + goles o ambos marcan) se liquidan exigiendo las dos condiciones. Un tiro al palo queda sin resolver si falta el dato de algún equipo, salvo que el otro ya registre uno. Con prórroga o penales se liquida a los 90 minutos: el marcador y también córners, tarjetas, remates y faltas (1T + 2T, de las estadísticas por periodo de Sportmonks); lo que no se publique por periodo queda sin resolver. Una predicción que siga sin poder liquidarse 7 días después del partido se anula; los partidos cancelados, abandonados o resueltos en mesa se anulan. Las props de jugador se emparejan por nombre completo (o apellido e inicial si hay un único candidato).
- Los parámetros del modelo por liga se ajustan con `python backtest.py --teams-file <liga.txt> --fit --save-params` y se guardan en `model_params.json`.
- **xG de Flashscore:** el modelo de goles mezcla los goles reales con el xG que Flashscore publica por partido (lo lee Firecrawl con la clave `FIRECRAWL_API_KEY`, inyectada por el proxy en la nube). Cada partido se lee una sola vez y se guarda en `history/flashscore_xg.json`, que `python track.py sync` sube junto al histórico. Si Firecrawl falla, el análisis sigue solo con goles.
- Para medir el xG: `python backtest.py --teams-file leagues/<liga>.txt --xg` (compara los mismos partidos con y sin xG). Las listas de equipos por liga están en `leagues/`.
- **Bajas:** el análisis lee las bajas del partido (Sportmonks) y, si un ausente sumaba el 10% o más de los goles y asistencias recientes de su equipo, lo anota en los riesgos. El descuento automático en goles esperados (`absence_weight`) está en 0: en el backtest de 838 partidos de 6 ligas no mejoró (`python backtest.py --teams-file leagues/<liga>.txt --injuries`).

## ⚡ MANEJO DE PARTIDOS EN VIVO
Si un equipo está jugando un partido en directo en este momento, el motor calcula el análisis con todos los partidos finalizados previos, excluyendo de forma automática los datos incompletos del partido en vivo.

---

## 🎯 FLUJO DE EJECUCIÓN OBLIGATORIO

1. Ejecuta el script oficial en la terminal:
   ```powershell
   python analyze.py "<Equipo 1> vs <Equipo 2>" --report
   ```
2. El script ejecuta el motor de cálculo, aplica estrictamente el `MarketPresentationCatalog` (descartando líneas triviales o > 88% y eligiendo la selección con mayor probabilidad dentro del rango 75.0% - 88.0%) y genera DIRECTAMENTE el reporte oficial adaptativo en formato Markdown.
3. **MUESTRA DIRECTAMENTE AL USUARIO EL REPORTE ADAPTATIVO OBTENIDO DEL COMANDO.**
   - Por defecto el comando imprime el **formato corto**: Pick Recomendado + "🔒 Las más seguras" (hasta 5 selecciones de 75% o más de Goles, Faltas, Remates, Tiros al arco, Córners o Resultado, sin mercados por mitad y como máximo 2 por categoría) + Proyecciones numéricas.
   - El reporte con todas las categorías (estructura de abajo) se pide con `--completo`. Todas las selecciones se registran igual en el histórico, marcadas como `pick` o `top5` cuando corresponde; `python track.py report` muestra su acierto por separado.
   ⛔ **ESTÁ ESTRICTAMENTE PROHIBIDO:**
   - No intentes deducir, inventar ni recalcular líneas a mano a partir de estadísticas crudas (NUNCA inventar Más de 0.5 goles, Más de 3.5 córners, Más de 1.5 córners ni Más de 0.5 tarjetas).
   - No muestres selecciones que no hayan sido validadas y devueltas por el comando oficial.

---

### Estructura del Reporte Completo (`--completo`):

# ⚽ <Equipo 1> vs <Equipo 2>
**Confianza:** <🟢 Alta / 🟡 Media / 🔴 Baja> (<Detalle breve: muestra de partidos, confirmación de alineación>)

### ⭐ PICK RECOMENDADO POR EL MODELO (AI Top Pick) *(si hay recomendación con prob ≥ 75.0%)*
• **<Selección con mayor solidez estadística> — XX.X%**  
  *Porque <justificación integral en 1 sola línea>.*

*(Despliega ÚNICAMENTE los bloques temáticos donde existan selecciones ≥ 75.0%):*

#### 🏆 Resultado *(si hay 1X2, Doble Oportunidad, DNB o Combos ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación táctica/estadística en 1 sola línea>.*

#### 🥅 Goles y Anotaciones *(si hay Goles Totales, Ambos Marcan, Multigoles o Goles de Equipo ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### ⏱️ Mercados por Mitad *(si hay 1T o 2T ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🚩 Córners *(si hay Córners Totales, de Equipo o 1T ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🟨 Tarjetas *(si hay Tarjetas Totales o de Equipo ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🛑 Faltas y Disciplina *(si hay Faltas Totales o de Equipo ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🎯 Remates y Tiros al Arco *(si hay Remates Totales, al Arco o de Equipo ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🚩 Fueras de Juego (Offsides) *(si hay Offsides Totales o de Equipo ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 💥 Especiales del Partido *(si hay Tiros al Poste / Woodwork ≥ 75%)*
• **<Selección con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 👟 Jugadores *(si hay Remates, Tiros al Arco o Goleadores de jugadores ≥ 75%)*
• **<Nombre Jugador> <Línea de remates/tiros al arco con prob ≥ 75.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*  
  *(Requiere confirmar titularidad oficial)*.

#### 📊 Proyecciones numéricas *(cierre de referencia matemática)*
• **Goles estimados:** X.XX (<Equipo 1>: X.XX | <Equipo 2>: X.XX)  
• **Córners estimados:** X.XX  
• **Tarjetas estimadas:** X.XX (árbitro <Nombre>: X.XX por partido en N, si está asignado)  
• **Remates estimados:** XX.X  
• **Marcador más probable:** X - X (XX.X%)
