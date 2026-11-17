# Histórico de predicciones DEPORT AI

Cada carpeta `AAAA-MM-DD/` guarda las predicciones emitidas ese día, **tal cual las imprimió**
`python analyze.py "<Local> vs <Visitante>" --report`, para contrastarlas luego con los resultados reales.

- `predicciones.json`: datos estructurados por partido (`fixture_id` de Sportmonks, equipos, hora UTC,
  confianza, pick recomendado, cada selección con su categoría y probabilidad, y proyecciones numéricas).
  Los campos `resultado` (por selección), `resultado_real` y `estado` empiezan en `null` / `PENDIENTE`
  y se completan al liquidar (`GANADA`, `PERDIDA` o `NULA`; estado `LIQUIDADO`).
- `reportes/*.md`: el reporte Markdown original completo de cada partido.

Las predicciones registradas no deben editarse después del inicio del partido; solo se rellenan los resultados.
