# Instrucciones para Claude (DEPORT AI)

Las reglas de pronósticos, el flujo de `analyze.py` y el histórico están en
[AGENTS.md](AGENTS.md): síguelas siempre.

## Código heredado o sin función (OBLIGATORIO)

- Siempre elimina el código heredado o sin función al tocar el proyecto: funciones,
  clases, módulos, campos de dataclass, parámetros, variables, imports, alias y
  opciones de línea de comandos que nadie usa, o que solo existen por
  "retrocompatibilidad" con algo ya retirado.
- No dejes código comentado, flags muertas ni ramas que nunca se ejecutan. Si una
  función queda reemplazada, borra la antigua en el mismo cambio.
- Antes de borrar, confirma que no tiene usos (`grep`, `vulture src *.py
  --min-confidence 60`, `ruff check src tests *.py --select F`). Los campos que se
  escriben en el histórico o en la salida JSON sí tienen función.
- Ajusta o elimina los tests que solo cubrían el código borrado y ejecuta
  `python -m pytest -q` antes de subir a `main`.
