# Reglas Oficiales de Pronósticos Deportivos (DEPORT AI)

Cuando el usuario pida analizar un partido, pronósticos o predicciones de fútbol (por ejemplo: "Analiza Real Madrid vs Barcelona", "ac milan vs venezia fc", "analiza alianza atletico vs comerciantes unidos", "¿Quién gana hoy?"):

## ⛔ PROHIBICIONES ESTRICTAS (BAJO NINGUNA CIRCUNSTANCIA INCLUIR):
1. **PROHIBIDO mostrar probabilidades menores al 60.0% (< 60.0%):** En NINGUNA categoría (goles, córners, tarjetas, remates, jugadores, hándicaps) se pueden incluir selecciones que no alcancen el 60.0%. La única excepción es el marcador exacto más probable dentro de las proyecciones numéricas.
2. **PROHIBIDO generar tablas:** No crees tablas markdown de goles, cuotas, edges ni comparativas de mercado.
3. **PROHIBIDO incluir "Mercados a Evitar" o "Trampas":** No generes ninguna sección ni viñeta de mercados a evitar, advertencias de valor negativo o trampas.
4. **PROHIBIDO mostrar variables matemáticas internas:** No menciones `shared_goal_component`, `W`, parámetros de interdependencia ni coeficientes crudos del modelo.
5. **PROHIBIDO incluir la Auditoría en Cascada (Waterfall Attribution):** No muestres desglose de Base Liga, Ventaja Local, Impacto Elo, etc.
6. **PROHIBIDO usar etiquetas de niveles:** No uses "(Nivel Oro)", "(Nivel Plata)" ni "(Banker)".
7. **PROHIBIDO generar muros de texto:** Cada selección debe llevar una justificación concisa de **exactamente una sola línea**, comenzando con `  *Porque ...*`.

## ⚡ MANEJO DE PARTIDOS EN VIVO
Si un equipo está jugando un partido en directo en este momento, el motor **calcula el análisis con todos los partidos finalizados previos**, excluyendo de forma automática los datos incompletos del partido en vivo para preservar la precisión matemática del modelo.

---

## FLUJO DE EJECUCIÓN
1. Ejecuta el script de cálculo interno en la terminal:
   ```powershell
   python analyze.py "<Equipo 1> vs <Equipo 2>" --json
   ```
2. Lee los datos JSON de DEPORT AI y filtra de manera estricta únicamente las selecciones con probabilidad ≥ 60.0%.
3. Genera el reporte siguiendo **EXACTAMENTE** esta estructura limpia, categorizada y visual:

---

# ⚽ <Equipo 1> vs <Equipo 2>
**Confianza:** <🟢 Alta / 🟡 Media / 🔴 Baja> (<Detalle breve: muestra de partidos, confirmación de alineación>)

#### 🥅 Resultado y goles
• **<Selección con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación táctica/estadística en 1 sola línea>.*

• **<Línea de goles con prob ≥ 60.0%> — XX.X%**  
  *Porque la proyección total de goles es de X.XX.*

#### 🚩 Córners
• **<Línea de córners con prob ≥ 60.0%> — XX.X%**  
  *Porque el modelo proyecta X.XX córners totales en el encuentro.*

• **<Córners de equipo con prob ≥ 60.0%> — XX.X%**  
  *Porque su proyección individual supera la línea esperada.*

#### 🟨 Tarjetas
• **<Línea de tarjetas con prob ≥ 60.0%> — XX.X%**  
  *Porque el total estimado de tarjetas es de X.XX.*

• **<Tarjetas de equipo con prob ≥ 60.0%> — XX.X%**  
  *Porque el modelo proyecta al menos X tarjetas para el equipo.*

#### 🎯 Remates y tiros a puerta
• **<Remates totales con prob ≥ 60.0%> — XX.X%**  
  *Porque se proyectan más de XX.X remates combinados entre ambos equipos.*

• **<Tiros a puerta con prob ≥ 60.0%> — XX.X%**  
  *Porque la proyección ofensiva supera esa línea.*

#### 👟 Jugadores
• **<Nombre Jugador> <Línea de remates/tiros al arco con prob ≥ 60.0%> — XX.X%**  
  *Porque su volumen proyectado respalda alcanzar esta línea.*  
  *(Requiere confirmar titularidad oficial)*.

#### 📊 Proyecciones numéricas
• **Goles estimados:** X.XX (<Equipo 1>: X.XX | <Equipo 2>: X.XX)  
• **Córners estimados:** X.XX  
• **Tarjetas estimadas:** X.XX  
• **Marcador más probable:** X - X (XX.X%)
