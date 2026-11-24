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
- Las props de jugador y los fueras de juego están suspendidos (no se publican) desde el 20/11/2026: en resultados reales acertaron 50% y 54% con 70%+ prometido. Los mercados por mitad también, desde el 21/11/2026 (61% con 67% prometido). Desde el 23/11/2026 también los córners del 1T (63% con 74%; son de mitades aunque se registren como Córners) y «quién saca más córners» (63% con 74%). Desde el 24/11/2026 también «equipo X tiene más tiros al arco» (61% en 23) y los «Menos de» de un solo equipo en córners (65% en 84) y tarjetas (70% en 47); los «Menos de» del total del partido siguen con su calibración propia.
- El mínimo publicado es 75% desde el 21/11/2026: en resultados reales el acierto siguió a la probabilidad (73% prometido, 73% acertado) y solo desde el 75% se acercaba al 80%.
- Máximo 5 selecciones publicadas y registradas por partido, contando el Pick (las 4 restantes son las más probables): las de un mismo partido caen juntas cuando el guion sale distinto. En resultados reales, 5 por partido acertó ~2 puntos más.
- La proyección de tarjetas combina a los equipos con el promedio de tarjetas del árbitro asignado (peso hasta 75%, menor si dirigió pocos partidos; validado en 543 partidos de 5 ligas). El reporte lo muestra en «Tarjetas estimadas» con su nombre, promedio y partidos dirigidos.

## 📒 HISTÓRICO DE PREDICCIONES (OBLIGATORIO)
- `analyze.py` registra automáticamente cada predicción y además la escribe en `history/predictions.jsonl`, dentro del repositorio. Es el histórico permanente: las sesiones en la nube son temporales y la base SQLite local se pierde al cerrarlas (se reconstruye sola desde ese archivo, y al reconstruirse recalcula la calibración).
- No uses `--no-track` salvo para pruebas.
- Solo se registran partidos que aún no empiezan. Re-analizar un partido antes del inicio reemplaza sus predicciones pendientes (no se acumulan las de cada análisis).
- **Después de cada análisis**, sube el histórico: `python track.py sync` (commit y push a `main`). Antes de exportar, `sync` trae `main` y fusiona su histórico y su caché de xG: una copia local vieja ya no pisa liquidaciones más recientes, y las predicciones se emparejan por mercado y selección, no por `id`. Reglas de la fusión: gana la liquidación más reciente (`settled_at`, que se actualiza con cada liquidación o corrección), y si ambas versiones siguen pendientes gana el análisis más reciente (`created_at`). Volver a registrar un partido borrado quita su marca de borrado, y un borrado solo se aplica si es posterior al registro del partido.
- Para comprobar con los resultados reales: `python track.py update` (liquida con Sportmonks), `python track.py report` y `python track.py sync`.
- Al empezar una sesión nueva, ejecuta primero `python track.py update` y `python track.py sync` para liquidar lo pendiente.
- Un partido registrado por error se borra con `python track.py remove <fixture_id> --reason "..."`: queda como línea de borrado en el histórico, así una copia vieja no lo vuelve a importar. El borrado recalcula la calibración en el momento.

## 🧪 CALIBRACIÓN Y PARÁMETROS
- La calibración dinámica solo se activa con **30 o más predicciones reales liquidadas** (ganadas o perdidas; las anuladas no cuentan) por categoría. Nunca se inventan datos para calibrar.
- La calibración se hace también por lado (Más/Menos) dentro de cada categoría, y lo que una liga aún no tiene se toma de la calibración global. Los «Menos de» de córners, tarjetas, tiros al arco, remates y faltas solo se publican cuando ese lado tiene su propia calibración (30+ liquidadas): en resultados reales acertaron 58-64% con 71-75% prometido.
- Córners «Más/Menos de» solo se publican con 2+ córners de distancia entre la proyección y la línea (80% de acierto con ese margen, 62% por debajo).
- El total del partido «Menos de» en goles (p. ej. «Menos de 3.5 goles») solo se publica cuando tiene su propia calibración (`Goles total|under`, 30+ liquidadas), y entonces se corrige con ese factor y no con el general de «Menos de» goles: acertó 67% con 78.7% prometido. Los «Menos de» de un equipo (82%) siguen publicándose.
- Freno por liga: una categoría cuyas últimas 20 predicciones liquidadas en una liga acertaron menos del 65% no se publica en esa liga (filas `<categoría>|recent` y `frozen_categories` del resumen de calibración). Mientras está frenada, hasta 2 de sus selecciones por partido se registran sin publicar (`unpublished = 1`): se liquidan y cuentan para la calibración y para levantar el freno, pero no salen en el reporte ni cuentan en el acierto publicado de `track.py report`. Al 24/11/2026 frena córners y goles de la Premier y goles de la Bundesliga. En consultas propias al histórico, filtra `unpublished = 0` para medir lo publicado.
- Además se calibra por tramo de probabilidad (60-65, 65-70, … 85-88 %, global, 30+ liquidadas por tramo): en resultados reales lo prometido al 85-88 % acertó ~79 % y arrastraba al Pick. El tramo se mide sobre la probabilidad previa al tramo (`prob_before_band`) y la categoría/lado sobre la del modelo (`model_prob`), que cada predicción guarda, para que ninguna corrección se anule a sí misma. El tope del 88 % se aplica antes del tramo. Las predicciones liquidadas antes del 22/11/2026 no guardan esas dos probabilidades: para el tramo no importa (entonces no había tramo y lo publicado era lo previo al tramo), pero la categoría/lado se mide ahí sobre lo publicado, que ya traía el ajuste de categoría; se corrige sola a medida que se liquidan predicciones nuevas. Desde el 24/11/2026 el acierto y la muestra de cada fila usan todas las liquidadas, pero el factor de corrección y el Brier se miden solo con las que guardan su probabilidad de etapa en cuanto son 30+; si no, con la aproximación anterior. La calibración se reescribe entera en cada recálculo.
- La corrección de sesgo de córners y tarjetas solo usa la proyección del **total del partido** (una vez por partido, 30+ partidos). Los goles esperados no se corrigen después de calcular la matriz de marcadores.
- Las combinadas (doble oportunidad + goles o ambos marcan) se liquidan exigiendo las dos condiciones. Un tiro al palo queda sin resolver si falta el dato de algún equipo, salvo que el otro ya registre uno. Con prórroga o penales se liquida a los 90 minutos: el marcador y también córners, tarjetas, remates y faltas (1T + 2T, de las estadísticas por periodo de Sportmonks); lo que no se publique por periodo queda sin resolver. Una predicción que siga sin poder liquidarse 7 días después del partido se anula; los partidos cancelados, abandonados o resueltos en mesa se anulan. Las props de jugador se emparejan por nombre completo (o apellido e inicial si hay un único candidato).
- La tabla manual de niveles de club (`CLUB_TIER_OFFSETS`, prior del Elo) se mantiene: en el backtest del 24/11/2026 (`backtest.py --club-tiers`) mejoró la calidad de las probabilidades de resultado en La Liga, Bundesliga, Eredivisie y Brasileirão, y solo en la Premier rindió mejor a media escala. Un club recibe su nivel solo si su nombre coincide entero (sin partículas como FC/AC ni números): así no se confunden homónimos de otros países ni filiales.
- Los parámetros del modelo por liga se ajustan con `python backtest.py --teams-file <liga.txt> --fit --save-params` y se guardan en `model_params.json`. Con `--synthetic` no se pueden guardar parámetros ni calibración (la liga simulada no tiene número de liga y el ajuste quedaba como global), y `--fit` no se combina con `--save-calibration` (se evaluaría con los mismos partidos del ajuste). Además, cada ajuste guardado registra sus partidos (`fitted_fixture_ids`) y `--save-calibration` los omite en cualquier ejecución posterior. Lo que guarda `--save-calibration` entra como no publicado, con la probabilidad del modelo como `model_prob`, y se exporta a `history/predictions.jsonl`: hay que subirlo con `python track.py sync` o se pierde al cerrar la sesión.
- **xG de Flashscore:** el modelo de goles mezcla los goles reales con el xG que Flashscore publica por partido (lo lee Firecrawl con la clave `FIRECRAWL_API_KEY`, inyectada por el proxy en la nube). Cada partido se lee una sola vez y se guarda en `history/flashscore_xg.json`, que `python track.py sync` sube junto al histórico. Si Firecrawl falla, el análisis sigue solo con goles.
- El backtest selecciona igual que el análisis real (Pick y luego máximo 5 por partido), pero sin la calibración dinámica: sale de resultados reales posteriores y usarla sería mirar el futuro.
- Para medir el xG: `python backtest.py --teams-file leagues/<liga>.txt --xg` (compara los mismos partidos con y sin xG). Las listas de equipos por liga están en `leagues/`.
- **Bajas:** el análisis lee las bajas del partido (Sportmonks) y, si un ausente sumaba el 10% o más de los goles y asistencias recientes de su equipo, lo anota en los riesgos. El descuento automático en goles esperados (`absence_weight`) está en 0: en el backtest de 838 partidos de 6 ligas no mejoró (`python backtest.py --teams-file leagues/<liga>.txt --injuries`).
- **Fuerza del once:** el modelo puede bajar los goles de un equipo (y subir los que concede) cuando su once es más débil que de costumbre, según los minutos recientes de cada jugador. El peso (`lineup_weight`) está en 0: en el backtest de 1107 partidos de 5 ligas empeoró en Bundesliga, Eredivisie y Premier, quedó igual en Brasileirão y mejoró apenas en LaLiga (`python backtest.py --teams-file leagues/<liga>.txt --lineups`). Además el once solo se publica unos 60 minutos antes del inicio.

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
   - Por defecto el comando imprime el **formato corto**: Pick Recomendado + "🎯 Alta confianza" (una selección por partido, la más probable entre tiros al arco del partido «Más de», faltas de un equipo «Más/Menos de» y remates del partido «Más de»: 89.5% en el histórico con el que se eligieron, en evaluación; `track.py report` muestra su acierto) + "🔒 Las más seguras" (hasta 4 selecciones de 75% o más de Goles, Faltas, Remates, Tiros al arco, Córners o Resultado, sin mercados por mitad y como máximo 2 por categoría) + Proyecciones numéricas.
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
