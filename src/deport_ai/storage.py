from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "deport_ai.db"
# Copia de texto del histórico dentro del repositorio: es la fuente permanente (las
# sesiones en la nube son temporales y la base SQLite se pierde al cerrarlas).
DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "history" / "predictions.jsonl"


class DatabaseManager:
    """Gestor de base de datos SQLite para persistencia y calibración dinámica de DEPORT AI."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        history_path: Path | str | None = None,
    ) -> None:
        self._memory_conn: sqlite3.Connection | None = None
        # El histórico en el repositorio se usa con la base por defecto (o si se indica);
        # las bases en memoria de las pruebas no lo tocan.
        if history_path is not None:
            self.history_path: Path | None = Path(history_path)
        elif db_path is None:
            self.history_path = DEFAULT_HISTORY_PATH
        else:
            self.history_path = None
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON")
        else:
            self.db_path = Path(db_path)

        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._sync_from_history()

    # ------------------------------------------------------------------ histórico
    def _sync_from_history(self) -> None:
        """Si la base no tiene un partido que sí está en el histórico, lo importa."""
        if self.history_path is None or not self.history_path.exists():
            return
        with self._get_connection() as conn:
            known = {row[0] for row in conn.execute("SELECT fixture_id FROM tracked_fixtures")}
            fixture_cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_fixtures)")}
            pred_cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_predictions)")}
            for line in self.history_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("fixture_id") in known:
                    continue
                fixture = {k: v for k, v in record.items() if k in fixture_cols}
                cols = ", ".join(fixture)
                conn.execute(
                    f"INSERT INTO tracked_fixtures ({cols}) VALUES ({', '.join('?' for _ in fixture)})",
                    list(fixture.values()),
                )
                for pred in record.get("predictions", []):
                    row = {k: v for k, v in pred.items() if k in pred_cols}
                    conn.execute(
                        f"INSERT INTO tracked_predictions ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                        list(row.values()),
                    )

    def export_history(self) -> Path | None:
        """Escribe todo el seguimiento (partidos + predicciones) en el histórico de texto."""
        if self.history_path is None:
            return None
        with self._get_connection() as conn:
            fixtures = [dict(r) for r in conn.execute("SELECT * FROM tracked_fixtures ORDER BY match_date, fixture_id")]
            preds: dict[int, list[dict[str, Any]]] = {}
            for r in conn.execute("SELECT * FROM tracked_predictions ORDER BY fixture_id, id"):
                preds.setdefault(r["fixture_id"], []).append(dict(r))
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for fixture in fixtures:
            fixture["predictions"] = preds.get(fixture["fixture_id"], [])
            lines.append(json.dumps(fixture, ensure_ascii=False))
        tmp = self.history_path.with_suffix(".tmp")
        tmp.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        tmp.replace(self.history_path)
        return self.history_path

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracked_fixtures (
                    fixture_id INTEGER PRIMARY KEY,
                    home_team_id INTEGER NOT NULL,
                    home_team_name TEXT NOT NULL,
                    away_team_id INTEGER NOT NULL,
                    away_team_name TEXT NOT NULL,
                    league_id INTEGER,
                    league_name TEXT,
                    match_date TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    actual_home_goals INTEGER,
                    actual_away_goals INTEGER,
                    actual_corners_home INTEGER,
                    actual_corners_away INTEGER,
                    actual_cards_home INTEGER,
                    actual_cards_away INTEGER,
                    actual_shots_home INTEGER,
                    actual_shots_away INTEGER,
                    actual_shots_on_home INTEGER,
                    actual_shots_on_away INTEGER,
                    actual_offsides_home INTEGER,
                    actual_offsides_away INTEGER,
                    actual_first_half_home_goals INTEGER,
                    actual_first_half_away_goals INTEGER,
                    actual_second_half_home_goals INTEGER,
                    actual_second_half_away_goals INTEGER,
                    woodwork_hit INTEGER,
                    player_stats_json TEXT,
                    settled_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tracked_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    market TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    line REAL,
                    side TEXT,
                    predicted_prob REAL NOT NULL,
                    odds REAL,
                    projection REAL,
                    basis TEXT,
                    explanation TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    pnl REAL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (fixture_id) REFERENCES tracked_fixtures (fixture_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS dynamic_calibration (
                    league_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    sample_size INTEGER NOT NULL DEFAULT 0,
                    hit_rate REAL NOT NULL DEFAULT 0.0,
                    brier_score REAL NOT NULL DEFAULT 0.0,
                    bias_offset REAL NOT NULL DEFAULT 0.0,
                    shrinkage_factor REAL NOT NULL DEFAULT 1.0,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY (league_id, category)
                );

                CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON tracked_predictions (fixture_id);
                CREATE INDEX IF NOT EXISTS idx_predictions_status ON tracked_predictions (status);
                CREATE INDEX IF NOT EXISTS idx_predictions_category ON tracked_predictions (category);
                CREATE INDEX IF NOT EXISTS idx_fixtures_status ON tracked_fixtures (status);
                CREATE INDEX IF NOT EXISTS idx_fixtures_league ON tracked_fixtures (league_id);
                """
            )

    def save_fixture_and_predictions(
        self,
        fixture_id: int,
        home_team_id: int,
        home_team_name: str,
        away_team_id: int,
        away_team_name: str,
        league_id: int | None,
        league_name: str | None,
        match_date: str | None,
        predictions: list[dict[str, Any]],
    ) -> None:
        """Guarda o actualiza un fixture y su lista de pronósticos recomendados."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tracked_fixtures (
                    fixture_id, home_team_id, home_team_name,
                    away_team_id, away_team_name, league_id,
                    league_name, match_date, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    home_team_name = excluded.home_team_name,
                    away_team_name = excluded.away_team_name,
                    league_id = excluded.league_id,
                    league_name = excluded.league_name,
                    match_date = excluded.match_date
                """,
                (
                    fixture_id,
                    home_team_id,
                    home_team_name,
                    away_team_id,
                    away_team_name,
                    league_id,
                    league_name,
                    match_date,
                    now_iso,
                ),
            )

            # Insertar únicamente pronósticos que no estén ya registrados para este fixture
            for p in predictions:
                sel = p.get("selection", "")
                market = p.get("market", "")
                exists = conn.execute(
                    """
                    SELECT 1 FROM tracked_predictions
                    WHERE fixture_id = ? AND market = ? AND selection = ?
                    """,
                    (fixture_id, market, sel),
                ).fetchone()

                if not exists:
                    conn.execute(
                        """
                        INSERT INTO tracked_predictions (
                            fixture_id, category, market, selection,
                            line, side, predicted_prob, odds,
                            projection, basis, explanation, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                        """,
                        (
                            fixture_id,
                            p.get("category", ""),
                            market,
                            sel,
                            p.get("line"),
                            p.get("side"),
                            float(p.get("probability", 0.0)),
                            p.get("odds"),
                            p.get("projection"),
                            p.get("basis"),
                            p.get("explanation"),
                            now_iso,
                        ),
                    )

    def get_pending_fixtures(self) -> list[dict[str, Any]]:
        """Fixtures por liquidar: pendientes, o cerrados que aún tienen predicciones pendientes."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tracked_fixtures
                WHERE status = 'PENDING'
                   OR fixture_id IN (SELECT fixture_id FROM tracked_predictions WHERE status = 'PENDING')
                ORDER BY match_date ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        """Obtiene un fixture por su identificador."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tracked_fixtures WHERE fixture_id = ?", (fixture_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_predictions_for_fixture(self, fixture_id: int) -> list[dict[str, Any]]:
        """Obtiene todas las predicciones asociadas a un fixture."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tracked_predictions
                WHERE fixture_id = ?
                ORDER BY id ASC
                """,
                (fixture_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_fixture_result(
        self,
        fixture_id: int,
        actual_stats: dict[str, Any],
        status: str = "FINISHED",
    ) -> None:
        """Actualiza las estadísticas finales reales de un fixture finalizado."""
        now_iso = datetime.now(timezone.utc).isoformat()
        player_stats_json = None
        if "player_stats" in actual_stats:
            player_stats_json = json.dumps(actual_stats["player_stats"], ensure_ascii=False)

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE tracked_fixtures SET
                    status = ?,
                    actual_home_goals = ?,
                    actual_away_goals = ?,
                    actual_corners_home = ?,
                    actual_corners_away = ?,
                    actual_cards_home = ?,
                    actual_cards_away = ?,
                    actual_shots_home = ?,
                    actual_shots_away = ?,
                    actual_shots_on_home = ?,
                    actual_shots_on_away = ?,
                    actual_offsides_home = ?,
                    actual_offsides_away = ?,
                    actual_first_half_home_goals = ?,
                    actual_first_half_away_goals = ?,
                    actual_second_half_home_goals = ?,
                    actual_second_half_away_goals = ?,
                    woodwork_hit = ?,
                    player_stats_json = COALESCE(?, player_stats_json),
                    settled_at = ?
                WHERE fixture_id = ?
                """,
                (
                    status,
                    actual_stats.get("home_goals"),
                    actual_stats.get("away_goals"),
                    actual_stats.get("corners_home"),
                    actual_stats.get("corners_away"),
                    actual_stats.get("cards_home"),
                    actual_stats.get("cards_away"),
                    actual_stats.get("shots_home"),
                    actual_stats.get("shots_away"),
                    actual_stats.get("shots_on_home"),
                    actual_stats.get("shots_on_away"),
                    actual_stats.get("offsides_home"),
                    actual_stats.get("offsides_away"),
                    actual_stats.get("first_half_home_goals"),
                    actual_stats.get("first_half_away_goals"),
                    actual_stats.get("second_half_home_goals"),
                    actual_stats.get("second_half_away_goals"),
                    actual_stats.get("woodwork_hit"),
                    player_stats_json,
                    now_iso,
                    fixture_id,
                ),
            )

    def update_prediction_status(
        self,
        prediction_id: int,
        status: str,
        pnl: float | None = None,
    ) -> None:
        """Actualiza el estado de una predicción (WON, LOST, VOID)."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE tracked_predictions
                SET status = ?, pnl = ?
                WHERE id = ?
                """,
                (status, pnl, prediction_id),
            )

    def get_settled_predictions(
        self,
        league_id: int | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Recupera predicciones liquidadas (WON, LOST, VOID) con métricas del fixture."""
        query = """
            SELECT
                p.*,
                f.home_team_name,
                f.away_team_name,
                f.league_id,
                f.league_name,
                f.match_date,
                f.actual_home_goals,
                f.actual_away_goals,
                f.actual_corners_home,
                f.actual_corners_away,
                f.actual_cards_home,
                f.actual_cards_away,
                f.actual_shots_home,
                f.actual_shots_away,
                f.actual_shots_on_home,
                f.actual_shots_on_away,
                f.actual_offsides_home,
                f.actual_offsides_away,
                f.actual_first_half_home_goals,
                f.actual_first_half_away_goals,
                f.actual_second_half_home_goals,
                f.actual_second_half_away_goals,
                f.woodwork_hit,
                f.player_stats_json
            FROM tracked_predictions p
            JOIN tracked_fixtures f ON p.fixture_id = f.fixture_id
            WHERE p.status IN ('WON', 'LOST', 'VOID')
        """
        params: list[Any] = []
        if league_id is not None:
            query += " AND f.league_id = ?"
            params.append(league_id)
        if category is not None:
            query += " AND p.category = ?"
            params.append(category)

        query += " ORDER BY f.match_date DESC, p.id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def save_calibration(
        self,
        league_id: int,
        category: str,
        sample_size: int,
        hit_rate: float,
        brier_score: float,
        bias_offset: float,
        shrinkage_factor: float,
    ) -> None:
        """Guarda o actualiza los parámetros de calibración adaptativa para una liga y categoría."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dynamic_calibration (
                    league_id, category, sample_size, hit_rate,
                    brier_score, bias_offset, shrinkage_factor, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, category) DO UPDATE SET
                    sample_size = excluded.sample_size,
                    hit_rate = excluded.hit_rate,
                    brier_score = excluded.brier_score,
                    bias_offset = excluded.bias_offset,
                    shrinkage_factor = excluded.shrinkage_factor,
                    last_updated = excluded.last_updated
                """,
                (
                    league_id,
                    category,
                    sample_size,
                    round(hit_rate, 4),
                    round(brier_score, 4),
                    round(bias_offset, 4),
                    round(shrinkage_factor, 4),
                    now_iso,
                ),
            )

    def purge_synthetic_seed(self) -> int:
        """Borra los partidos ficticios que generaba el antiguo auto-seed de calibración.

        Se identifican por la firma exacta que usaba ese código: visitante 'Visitante'
        y liga 'Liga'. Devuelve el número de partidos eliminados.
        """
        with self._get_connection() as conn:
            ids = [
                row[0]
                for row in conn.execute(
                    "SELECT fixture_id FROM tracked_fixtures "
                    "WHERE away_team_name = 'Visitante' AND league_name = 'Liga'"
                ).fetchall()
            ]
            if not ids:
                return 0
            marks = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM tracked_predictions WHERE fixture_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM tracked_fixtures WHERE fixture_id IN ({marks})", ids)
            return len(ids)

    def clear_calibration(self) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM dynamic_calibration")

    def get_calibration(
        self,
        league_id: int | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recupera factores de calibración registrados."""
        query = "SELECT * FROM dynamic_calibration WHERE 1=1"
        params: list[Any] = []
        if league_id is not None:
            query += " AND league_id = ?"
            params.append(league_id)
        if category is not None:
            query += " AND category = ?"
            params.append(category)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_summary_stats(self) -> dict[str, Any]:
        """Obtiene un resumen cuantitativo global del rendimiento."""
        with self._get_connection() as conn:
            total_pred = conn.execute("SELECT COUNT(*) FROM tracked_predictions").fetchone()[0]
            won = conn.execute("SELECT COUNT(*) FROM tracked_predictions WHERE status = 'WON'").fetchone()[0]
            lost = conn.execute("SELECT COUNT(*) FROM tracked_predictions WHERE status = 'LOST'").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM tracked_predictions WHERE status = 'PENDING'").fetchone()[0]
            void = conn.execute("SELECT COUNT(*) FROM tracked_predictions WHERE status = 'VOID'").fetchone()[0]

            resolved = won + lost
            hit_rate = (won / resolved) if resolved > 0 else 0.0

            # Hit rate por categoría
            cat_rows = conn.execute(
                """
                SELECT
                    category,
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'WON' THEN 1 ELSE 0 END) as won,
                    SUM(CASE WHEN status = 'LOST' THEN 1 ELSE 0 END) as lost,
                    SUM(CASE WHEN status = 'VOID' THEN 1 ELSE 0 END) as void,
                    AVG(predicted_prob) as avg_prob
                FROM tracked_predictions
                WHERE status IN ('WON', 'LOST', 'VOID')
                GROUP BY category
                ORDER BY total DESC
                """
            ).fetchall()

            by_category = []
            for r in cat_rows:
                r_resolved = r["won"] + r["lost"]
                c_hit = (r["won"] / r_resolved) if r_resolved > 0 else 0.0
                by_category.append(
                    {
                        "category": r["category"],
                        "total": r["total"],
                        "won": r["won"],
                        "lost": r["lost"],
                        "void": r["void"],
                        "hit_rate": round(c_hit, 4),
                        "avg_predicted_prob": round(r["avg_prob"] or 0.0, 4),
                    }
                )

            return {
                "total_predictions": total_pred,
                "resolved": resolved,
                "won": won,
                "lost": lost,
                "pending": pending,
                "void": void,
                "overall_hit_rate": round(hit_rate, 4),
                "by_category": by_category,
            }
