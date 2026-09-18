---
description: Guía y plantilla oficial de predicciones deportivas con DEPORT AI
globs: *
---

# Instrucciones de Análisis de Pronósticos Deportivos

Cuando el usuario pida analizar un partido, pronósticos o predicciones de fútbol (por ejemplo: "Analiza Real Madrid vs Barcelona", "ac milan vs venezia fc", "analiza los sevilla fc vs atletico madrid", "¿Quién gana hoy?"):

> ⛔ **PROHIBICIONES ESTRICTAS (NO INCLUIR):**
> 1. **ESTÁ ESTRICTAMENTE PROHIBIDO incluir la sección de 'MERCADOS A EVITAR', 'MERCADOS PROHIBIDOS' o 'TRAMPAS'.** No generes ninguna sección ni viñeta de mercados a evitar.
> 2. **ESTÁ ESTRICTAMENTE PROHIBIDO usar etiquetas como '(Nivel Oro)', '(Nivel Plata)' o '(Banker)'.**
> 3. **ESTÁ ESTRICTAMENTE PROHIBIDO inventar o alterar el formato.**
> 4. **ESTÁ ESTRICTAMENTE PROHIBIDO incluir apuestas, líneas o selecciones con probabilidad inferior al 60.0% (< 60.0%).** Ningún mercado, línea de volumen o prop de jugador puede mostrarse con probabilidad menor al 60.0% (excepto el marcador exacto en las proyecciones numéricas). Si una línea no alcanza el 60.0%, queda descartada de forma tajante.
> 5. **ESTÁ ESTRICTAMENTE PROHIBIDO generar muros de texto o explicaciones largas.** Cada selección debe llevar una justificación concisa de **exactamente una sola línea**, comenzando con `  *Porque ...*`.

> ⚡ **MANEJO DE PARTIDOS EN VIVO:** Si un equipo está jugando un partido en directo en este momento, el motor **calcula el análisis con todos los partidos finalizados previos**, excluyendo de forma automática los datos incompletos del partido en vivo para preservar la precisión matemática del modelo.

1. Ejecuta el script de cálculo interno en terminal:
   ```powershell
   python analyze.py "<Equipo 1> vs <Equipo 2>" --json
   ```
2. Con los datos obtenidos del JSON de DEPORT AI, genera el reporte oficial siguiendo EXACTAMENTE esta estructura limpia, categorizada y concisa:

---

# ⚽ <Equipo 1> vs <Equipo 2>
**Confianza:** <🟢 Alta / 🟡 Media / 🔴 Baja> (<Detalle breve: alineación confirmada/proyectada, muestra de partidos>)

#### 🥅 Resultado y goles
• **<Selección de Resultado o Doble Oportunidad con prob ≥ 60.0%> — XX.X%**  
  *Porque <motivo táctico/estadístico conciso en 1 sola línea>.*

• **Más de 1.5 goles — XX.X%**  
  *Porque la proyección total de goles es de X.XX.*

• **<Otra selección de goles o 2T con prob ≥ 60.0%> — XX.X%**  
  *Porque <justificación concisa en 1 sola línea>.*

#### 🚩 Córners
• **<Línea Córners Totales (ej. Más de 7.5 córners con prob ≥ 60.0%)> — XX.X%**  
  *Porque el modelo proyecta X.XX córners totales en el encuentro.*

• **<Córners por Equipo con prob ≥ 60.0%> — XX.X%**  
  *Porque su proyección individual supera la línea de X.5 córners.*

#### 🟨 Tarjetas
• **<Línea Tarjetas Totales (ej. Más de 3.5 tarjetas con prob ≥ 60.0%)> — XX.X%**  
  *Porque el total estimado de tarjetas es de X.XX.*

• **<Tarjetas de Equipo con prob ≥ 60.0%> — XX.X%**  
  *Porque el modelo proyecta al menos X tarjetas para el equipo.*

#### 🎯 Remates y tiros a puerta
• **<Remates Totales con prob ≥ 60.0%> — XX.X%**  
  *Porque se proyectan más de XX.X remates combinados entre ambos equipos.*

• **<Tiros a Puerta con prob ≥ 60.0%> — XX.X%**  
  *Porque la proyección ofensiva supera esa línea.*

#### 👟 Jugadores
• **<Nombre Jugador> <Línea de remates o tiros al arco con prob ≥ 60.0%> — XX.X%**  
  *Porque su volumen proyectado respalda alcanzar esta línea.*  
  *(Requiere confirmar titularidad oficial)*.

#### 📊 Proyecciones numéricas
• **Goles estimados:** X.XX (<Equipo 1>: X.XX | <Equipo 2>: X.XX)  
• **Córners estimados:** X.XX  
• **Tarjetas estimadas:** X.XX  
• **Marcador más probable:** X - X (XX.X%)



