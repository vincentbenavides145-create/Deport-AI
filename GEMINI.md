# Reglas Oficiales de Pronósticos Deportivos (DEPORT AI)

Cuando el usuario pida analizar un partido, pronósticos o predicciones de fútbol (por ejemplo: "Analiza Real Madrid vs Barcelona", "ac milan vs venezia fc", "analiza alianza atletico vs comerciantes unidos", "¿Quién gana hoy?"):

## ⛔ PROHIBICIONES ESTRICTAS (BAJO NINGUNA CIRCUNSTANCIA INCLUIR):
1. **PROHIBIDO mostrar probabilidades menores al 60.0% (< 60.0%):** En NINGUNA categoría (goles, córners, tarjetas, remates, jugadores, hándicaps, mitades, fueras de juego, etc.) se pueden incluir selecciones que no alcancen el 60.0%. La única excepción es el marcador exacto más probable dentro de las proyecciones numéricas.
2. **PROHIBIDO generar tablas:** No crees tablas markdown de goles, cuotas, edges ni comparativas de mercado.
3. **PROHIBIDO incluir "Mercados a Evitar" o "Trampas":** No generes ninguna sección ni viñeta de mercados a evitar, advertencias de valor negativo o trampas.
4. **PROHIBIDO mostrar variables matemáticas internas:** No menciones `shared_goal_component`, `W`, parámetros de interdependencia ni coeficientes crudos del modelo.
5. **PROHIBIDO incluir la Auditoría en Cascada (Waterfall Attribution):** No muestres desglose de Base Liga, Ventaja Local, Impacto Elo, etc.
6. **PROHIBIDO usar etiquetas de niveles:** No uses "(Nivel Oro)", "(Nivel Plata)" ni "(Banker)".
7. **PROHIBIDO generar muros de texto:** Cada selección debe llevar una justificación concisa de **exactamente una sola línea**, comenzando con `  *Porque ...*`.
8. **PROHIBIDO forzar categorías vacías (ESTRUCTURA ADAPTATIVA):** Si en una categoría no hay selecciones que alcancen el 60.0%, **NO muestres ese encabezado**. La respuesta debe fluir únicamente con los mercados donde el partido realmente ofrezca solidez estadística.

## ⚡ MANEJO DE PARTIDOS EN VIVO
Si un equipo está jugando un partido en directo en este momento, el motor calcula el análisis con todos los partidos finalizados previos, excluyendo de forma automática los datos incompletos del partido en vivo.

---

## 🎯 FLUJO DE EJECUCIÓN Y ESTRUCTURA ADAPTATIVA (CATÁLOGO BETANO)

1. Ejecuta el script de cálculo interno en la terminal:
   ```powershell
   python analyze.py "<Equipo 1> vs <Equipo 2>" --json
   ```
2. Lee los datos JSON de DEPORT AI y filtra de manera estricta únicamente las selecciones con probabilidad ≥ 60.0%.
3. Genera un reporte **completamente adaptativo** según las probabilidades, estadísticas y la amplia oferta de mercados disponibles (estilo Betano):

### Estructura Dinámica:

# ⚽ <Equipo 1> vs <Equipo 2>
**Confianza:** <🟢 Alta / 🟡 Media / 🔴 Baja> (<Detalle breve: muestra de partidos, confirmación de alineación>)

*(Despliega ÚNICAMENTE los bloques temáticos donde existan selecciones ≥ 60.0%):*

#### 🏆 Resultado y Hándicap *(si hay 1X2, Doble Oportunidad, DNB o Hándicap Asiático ≥ 60%)*
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

#### 🎯 Remates y Tiros a Puerta *(si hay Remates Totales, al Arco o de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 🚩 Fueras de Juego (Offsides) *(si hay Offsides Totales o de Equipo ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 💥 Especiales del Partido *(si hay Tiros al Poste / Woodwork ≥ 60%)*
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*

#### 👟 Jugadores *(si hay Remates, Tiros a Puerta o Goleadores de jugadores ≥ 60%)*
• **<Nombre Jugador> <Línea de remates/tiros al arco con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación en 1 sola línea>.*  
  *(Requiere confirmar titularidad oficial)*.

#### 📊 Proyecciones numéricas *(cierre de referencia matemática)*
• **Goles estimados:** X.XX (<Equipo 1>: X.XX | <Equipo 2>: X.XX)  
• **Córners estimados:** X.XX  
• **Tarjetas estimadas:** X.XX  
• **Remates estimados:** XX.X  
• **Marcador más probable:** X - X (XX.X%)
