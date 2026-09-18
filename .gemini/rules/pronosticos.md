---
description: Guía y plantilla oficial de predicciones deportivas con DEPORT AI
globs: *
---

# Instrucciones de Análisis de Pronósticos Deportivos

Cuando el usuario pida analizar un partido, pronósticos o predicciones de fútbol (por ejemplo: "Analiza Real Madrid vs Barcelona", "ac milan vs venezia fc", "analiza los sevilla fc vs atletico madrid", "¿Quién gana hoy?"):

> ⛔ **PROHIBICIONES ESTRICTAS (NO INCLUIR):**
> 1. **ESTÁ ESTRICTAMENTE PROHIBIDO incluir la sección de 'MERCADOS A EVITAR', 'MERCADOS PROHIBIDOS' o 'TRAMPAS'.** No generes ninguna sección ni viñeta de mercados a evitar.
> 2. **ESTÁ ESTRICTAMENTE PROHIBIDO usar etiquetas como '(Nivel Oro)', '(Nivel Plata)' o '(Banker)'.** Usa únicamente los títulos limpios: `🟢 1. PICK PRINCIPAL`, `🔵 2. PICK SECUNDARIO / VALOR`.
> 3. **ESTÁ ESTRICTAMENTE PROHIBIDO inventar o alterar el formato.**

> ⚡ **MANEJO DE PARTIDOS EN VIVO:** Si un equipo está jugando un partido en directo en este momento, el motor **calcula el análisis con todos los partidos finalizados previos**, excluyendo de forma automática los datos incompletos del partido en vivo para preservar la precisión matemática del modelo.

1. Ejecuta el script de cálculo interno en terminal:
   ```powershell
   python analyze.py "<Equipo 1> vs <Equipo 2>" --json
   ```
2. Con los datos obtenidos del JSON de DEPORT AI, genera el reporte oficial explicando con claridad **el por qué de cada selección y el análisis de su cuota**, siguiendo EXACTAMENTE esta estructura limpia (SIN mercados a evitar y SIN etiquetas de nivel oro/plata):

---

# ⚽ Pronóstico Oficial: <Equipo 1> vs. <Equipo 2>
**Competición:** <Nombre de Liga / Torneo> • <Estadio>  
**Confianza Epistémica:** <🟢 ALTA / 🟡 MEDIA / 🔴 BAJA (XX/100)> • <Muestra: XX partidos, alineación confirmada/proyectada>  
**xG Proyectado:** <Equipo 1> X.XX — <Equipo 2> X.XX (Total: X.XX goles)  
**Auditoría xG (Waterfall):** Base Liga: ±X.XX | Ventaja Sede: ±X.XX | Impacto Elo: ±X.XX | Forma Reciente: ±X.XX | Descanso: ±X.XX

---

## 🎯 Picks Principales y Argumentación de Valor

### 🟢 1. PICK PRINCIPAL: <Selección de mayor certeza, ej. Doble Oportunidad 1X> — **XX.X%**
- **Cuota Justa:** **@X.XX** | **Probabilidad del Modelo:** **XX.X%**
- 💡 **¿Por qué esta apuesta?:** <Explicación táctica y estadística concisa del por qué ocurre este escenario>.
- 💰 **Análisis de Cuota:** <Explicación de por qué esta cuota es rentable y segura para el apostador>.

---

### 🔵 2. PICK SECUNDARIO / VALOR: <Selección complementaria, ej. Hándicap Asiático o DNB> — **XX.X%**
- **Cuota Justa:** **@X.XX** | **Probabilidad del Modelo:** **XX.X%**
- 💡 **¿Por qué esta apuesta?:** <Motivo táctico/estadístico del rendimiento reciente o por sede>.
- 💰 **Análisis de Cuota:** <Explicación del valor esperado positivo (+EV) de la cuota>.

---

### 👟 3. JUGADOR DEL PARTIDO: **<Nombre Jugador>** (<Equipo>) **2+ Remates Totales** — **XX.X%**
- **Probabilidad:** 2+ Tiros: **XX.X%** | 3+ Tiros: **XX.X%**
- 💡 **¿Por qué esta apuesta?:** <Promedio de tiros por partido del jugador y concesión de tiros del rival>.

---

### 🎯 4. MARCADOR EXACTO OFICIAL: **<Marcador #1, ej. 1 - 1>** (**XX.X%**) *(Alt: <#2> a XX% / <#3> a XX%)*
- 💡 **¿Por qué este marcador?:** <Razón del cruce del modelo Poisson bivariado y xG proyectado>.

---

### 🔥 5. BET BUILDER RECOMENDADO (Cuota aprox. @X.XX):
**[ <Selección 1> + <Selección 2> + <Selección 3 (Tiros jugador)> ]**
- 💡 **¿Por qué esta combinada?:** <Explicación de la correlación positiva entre los 3 eventos>.

---

## 📊 Datos Clave Complementarios
- ⚽ **Goles Totales:** Más de 1.5 Goles (**XX.X%**) | Más de 0.5 Goles en 1T (**XX.X%**)
- ⛳ **Córners Esperados:** **X.XX** *(<Equipo 1>: X.XX \| <Equipo 2>: X.XX)* ➔ <Línea destacada>
- 🟨 **Tarjetas Esperadas:** **X.XX** *(<Equipo 1>: X.XX \| <Equipo 2>: X.XX)*
- 🚩 **Fueras de Juego (Offsides):** **X.XX**
- ⚔️ **Rivales Comunes:** <Resumen de 1 línea del balance o ventaja neta ante mismos rivales>.
- 🛡️ **Factores Clave / Riesgos:** <Bajas, alineaciones y lectura táctica>.



