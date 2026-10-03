from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketDefinition:
    """Definición declarativa e inmutable de un mercado estadístico del modelo."""

    id: str
    category: str
    group: str
    selection_template: str
    market_template: str
    line: float | None
    side: str  # "over", "under", "1x2", "binary", "player"
    probability_source: str
    projection_source: str | None
    explanation_template: str
    minimum_probability: float = 0.60
    requires_starter_confirmation: bool = False
    is_experimental: bool = False


MINIMUM_INFORMATIVE_LINES: dict[str, float] = {
    "cards_total": 1.5,
    "cards_home": 0.5,
    "cards_away": 0.5,
    "corners_total": 3.5,
    "corners_home": 1.5,
    "corners_away": 1.5,
    "shots_total": 15.5,
    "shots_home": 7.5,
    "shots_away": 7.5,
    "shots_on_total": 4.5,
    "shots_on_home": 2.5,
    "shots_on_away": 2.5,
    "offsides_total": 1.5,
    "offsides_home": 0.5,
    "offsides_away": 0.5,
    "goals_total": 0.5,
    "goals_home": 0.5,
    "goals_away": 0.5,
    "fouls_total": 20.5,
    "fouls_home": 9.5,
    "fouls_away": 9.5,
    "corners_first_half": 2.5,
}


def build_declarative_catalog(home_name: str, away_name: str) -> list[MarketDefinition]:
    """Construye el catálogo declarativo completo e independiente de cualquier casa."""
    catalog: list[MarketDefinition] = []

    # 1. Tarjetas Totales (Mínima informativa: +1.5)
    for line in [1.5, 2.5, 3.5, 4.5, 5.5]:
        catalog.append(
            MarketDefinition(
                id=f"cards_total_over_{int(line*10)}",
                category="Tarjetas",
                group="cards_total",
                selection_template=f"Más de {line} tarjetas",
                market_template="Tarjetas totales",
                line=line,
                side="over",
                probability_source="neg_bin_cards_total",
                projection_source="total_cards",
                explanation_template="Porque el modelo proyecta {projection:.2f} tarjetas totales.",
            )
        )
    for line in [3.5, 4.5, 5.5]:
        catalog.append(
            MarketDefinition(
                id=f"cards_total_under_{int(line*10)}",
                category="Tarjetas",
                group="cards_total",
                selection_template=f"Menos de {line} tarjetas",
                market_template="Tarjetas totales",
                line=line,
                side="under",
                probability_source="neg_bin_cards_total",
                projection_source="total_cards",
                explanation_template="Porque el modelo proyecta un volumen contenido de {projection:.2f} tarjetas totales.",
            )
        )

    # Tarjetas de Equipo (Local y Visitante, Mínima informativa: +0.5)
    for team_prefix, team_name, prob_src, proj_src in [
        ("cards_home", home_name, "neg_bin_cards_home", "cards_home"),
        ("cards_away", away_name, "neg_bin_cards_away", "cards_away"),
    ]:
        for line in [0.5, 1.5, 2.5, 3.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Tarjetas",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} tarjetas",
                    market_template=f"Tarjetas de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} tarjetas para {team_name}.",
                )
            )
        for line in [1.5, 2.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Tarjetas",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} tarjetas",
                    market_template=f"Tarjetas de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} tarjetas para {team_name}.",
                )
            )

    # Tarjetas: Mercados combinados y comparativos (Creativos)
    catalog.extend([
        MarketDefinition(
            id="both_teams_card",
            category="Tarjetas",
            group="both_teams_card",
            selection_template="Ambos equipos reciben al menos 1 tarjeta",
            market_template="Ambos equipos reciben tarjeta",
            line=0.5,
            side="binary",
            probability_source="both_teams_card",
            projection_source="total_cards",
            explanation_template="Porque ambos equipos promedian suficiente fricción para que ambos sean amonestados.",
        ),
        MarketDefinition(
            id="both_teams_2_cards",
            category="Tarjetas",
            group="both_teams_2_cards",
            selection_template="Ambos equipos reciben 2+ tarjetas",
            market_template="Ambos equipos reciben 2+ tarjetas",
            line=1.5,
            side="binary",
            probability_source="both_teams_2_cards",
            projection_source="total_cards",
            explanation_template="Porque la intensidad del partido proyecta múltiples tarjetas para ambos bandos.",
        ),
        MarketDefinition(
            id="cards_1x2_home",
            category="Tarjetas",
            group="cards_1x2",
            selection_template=f"{home_name} recibe más tarjetas",
            market_template="Tarjetas 1X2",
            line=None,
            side="1x2",
            probability_source="cards_1x2_home",
            projection_source="cards_home",
            explanation_template=f"Porque el modelo proyecta un mayor índice disciplinario para {home_name}.",
        ),
        MarketDefinition(
            id="cards_1x2_away",
            category="Tarjetas",
            group="cards_1x2",
            selection_template=f"{away_name} recibe más tarjetas",
            market_template="Tarjetas 1X2",
            line=None,
            side="1x2",
            probability_source="cards_1x2_away",
            projection_source="cards_away",
            explanation_template=f"Porque el modelo proyecta un mayor índice disciplinario para {away_name}.",
        ),
    ])

    # 2. Córners Totales (Mínima informativa: +3.5)
    for line in [3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5]:
        catalog.append(
            MarketDefinition(
                id=f"corners_total_over_{int(line*10)}",
                category="Córners",
                group="corners_total",
                selection_template=f"Más de {line} córners",
                market_template="Córners totales",
                line=line,
                side="over",
                probability_source="neg_bin_corners_total",
                projection_source="total_corners",
                explanation_template="Porque el modelo proyecta {projection:.2f} córners totales.",
            )
        )
    for line in [8.5, 9.5, 10.5, 11.5]:
        catalog.append(
            MarketDefinition(
                id=f"corners_total_under_{int(line*10)}",
                category="Córners",
                group="corners_total",
                selection_template=f"Menos de {line} córners",
                market_template="Córners totales",
                line=line,
                side="under",
                probability_source="neg_bin_corners_total",
                projection_source="total_corners",
                explanation_template="Porque el modelo proyecta un volumen contenido de {projection:.2f} córners totales.",
            )
        )

    # Córners de Equipo (Mínima informativa: +1.5)
    for team_prefix, team_name, prob_src, proj_src in [
        ("corners_home", home_name, "neg_bin_corners_home", "corners_home"),
        ("corners_away", away_name, "neg_bin_corners_away", "corners_away"),
    ]:
        for line in [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Córners",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} córners",
                    market_template=f"Córners de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} saques de esquina para {team_name}.",
                )
            )
        for line in [3.5, 4.5, 5.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Córners",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} córners",
                    market_template=f"Córners de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} saques de esquina para {team_name}.",
                )
            )

    # Córners 1X2
    catalog.append(
        MarketDefinition(
            id="corners_1x2_home",
            category="Córners",
            group="corners_1x2",
            selection_template=f"{home_name} saca más córners (Experimental)",
            market_template="Córners 1X2",
            line=None,
            side="1x2",
            probability_source="corners_1x2_home",
            projection_source="corners_home",
            explanation_template=f"Porque el modelo proyecta {{projection:.2f}} córners para {home_name}, dominando el ataque por bandas.",
            is_experimental=True,
        )
    )
    catalog.append(
        MarketDefinition(
            id="corners_1x2_away",
            category="Córners",
            group="corners_1x2",
            selection_template=f"{away_name} saca más córners (Experimental)",
            market_template="Córners 1X2",
            line=None,
            side="1x2",
            probability_source="corners_1x2_away",
            projection_source="corners_away",
            explanation_template=f"Porque el modelo proyecta {{projection:.2f}} córners para {away_name}, dominando el ataque por bandas.",
            is_experimental=True,
        )
    )

    # Córners combinados
    catalog.extend([
        MarketDefinition(
            id="both_teams_corners_3",
            category="Córners",
            group="both_teams_corners",
            selection_template="Ambos equipos sacan 3+ córners",
            market_template="Ambos equipos sacan córners",
            line=2.5,
            side="binary",
            probability_source="both_teams_corners_3",
            projection_source="total_corners",
            explanation_template="Porque ambos equipos despliegan juego por bandas alcanzando el umbral de 3 córners.",
        ),
        MarketDefinition(
            id="both_teams_corners_4",
            category="Córners",
            group="both_teams_corners",
            selection_template="Ambos equipos sacan 4+ córners",
            market_template="Ambos equipos sacan córners",
            line=3.5,
            side="binary",
            probability_source="both_teams_corners_4",
            projection_source="total_corners",
            explanation_template="Porque ambos conjuntos sostienen alta generación ofensiva desde los costados.",
        ),
    ])

    # 3. Remates Totales (Mínima informativa: +15.5)
    for line in [15.5, 17.5, 19.5, 21.5, 23.5, 25.5, 27.5, 29.5]:
        catalog.append(
            MarketDefinition(
                id=f"shots_total_over_{int(line*10)}",
                category="Remates",
                group="shots_total",
                selection_template=f"Más de {line} remates",
                market_template="Remates totales",
                line=line,
                side="over",
                probability_source="neg_bin_shots_total",
                projection_source="total_shots",
                explanation_template="Porque el modelo proyecta {projection:.1f} remates totales en el encuentro.",
            )
        )
    for line in [22.5, 24.5, 26.5, 28.5]:
        catalog.append(
            MarketDefinition(
                id=f"shots_total_under_{int(line*10)}",
                category="Remates",
                group="shots_total",
                selection_template=f"Menos de {line} remates",
                market_template="Remates totales",
                line=line,
                side="under",
                probability_source="neg_bin_shots_total",
                projection_source="total_shots",
                explanation_template="Porque el modelo proyecta {projection:.1f} remates totales.",
            )
        )

    # Remates de Equipo (Mínima informativa: +7.5)
    for team_prefix, team_name, prob_src, proj_src in [
        ("shots_home", home_name, "neg_bin_shots_home", "total_shots_home"),
        ("shots_away", away_name, "neg_bin_shots_away", "total_shots_away"),
    ]:
        for line in [7.5, 9.5, 10.5, 11.5, 12.5, 13.5, 15.5, 17.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Remates",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} remates",
                    market_template=f"Remates de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.1f}} disparos para {team_name}.",
                )
            )
        for line in [8.5, 9.5, 10.5, 11.5, 12.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Remates",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} remates",
                    market_template=f"Remates de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta un volumen contenido de {{projection:.1f}} remates para {team_name}.",
                )
            )

    # 4. Tiros a Puerta Totales (Mínima informativa: +4.5)
    for line in [4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5]:
        catalog.append(
            MarketDefinition(
                id=f"shots_on_total_over_{int(line*10)}",
                category="Tiros a puerta",
                group="shots_on_total",
                selection_template=f"Más de {line} tiros a puerta",
                market_template="Tiros a puerta totales",
                line=line,
                side="over",
                probability_source="neg_bin_shots_on_total",
                projection_source="total_shots_on",
                explanation_template="Porque el modelo proyecta {projection:.1f} tiros a puerta totales.",
            )
        )
    for line in [7.5, 8.5, 9.5]:
        catalog.append(
            MarketDefinition(
                id=f"shots_on_total_under_{int(line*10)}",
                category="Tiros a puerta",
                group="shots_on_total",
                selection_template=f"Menos de {line} tiros a puerta",
                market_template="Tiros a puerta totales",
                line=line,
                side="under",
                probability_source="neg_bin_shots_on_total",
                projection_source="total_shots_on",
                explanation_template="Porque el modelo proyecta {projection:.1f} tiros a puerta totales.",
            )
        )

    # Tiros a Puerta de Equipo (Mínima informativa: +2.5)
    for team_prefix, team_name, prob_src, proj_src in [
        ("shots_on_home", home_name, "neg_bin_shots_on_home", "shots_on_home"),
        ("shots_on_away", away_name, "neg_bin_shots_on_away", "shots_on_away"),
    ]:
        for line in [2.5, 3.5, 4.5, 5.5, 6.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Tiros a puerta",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} tiros a puerta",
                    market_template=f"Tiros a puerta de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.1f}} tiros a puerta para {team_name}.",
                )
            )
        for line in [2.5, 3.5, 4.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Tiros a puerta",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} tiros a puerta",
                    market_template=f"Tiros a puerta de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.1f}} tiros a puerta para {team_name}.",
                )
            )

    # Tiros a puerta: Mercados combinados y comparativos (Creativos)
    catalog.extend([
        MarketDefinition(
            id="both_teams_shots_on_3",
            category="Tiros a puerta",
            group="both_teams_shots_on",
            selection_template="Ambos equipos tienen 3+ tiros a puerta",
            market_template="Tiros a puerta combinados",
            line=2.5,
            side="binary",
            probability_source="both_teams_shots_on_3",
            projection_source="total_shots_on",
            explanation_template="Porque ambos equipos proyectan suficiente pegada para sumar al menos 3 tiros entre los tres palos.",
        ),
        MarketDefinition(
            id="shots_on_1x2_home",
            category="Tiros a puerta",
            group="shots_on_1x2",
            selection_template=f"{home_name} tiene más tiros a puerta",
            market_template="Tiros a puerta 1X2",
            line=None,
            side="1x2",
            probability_source="shots_on_1x2_home",
            projection_source="shots_on_home",
            explanation_template=f"Porque {home_name} genera mayor frecuencia de remates francos al arco rival.",
        ),
        MarketDefinition(
            id="shots_on_1x2_away",
            category="Tiros a puerta",
            group="shots_on_1x2",
            selection_template=f"{away_name} tiene más tiros a puerta",
            market_template="Tiros a puerta 1X2",
            line=None,
            side="1x2",
            probability_source="shots_on_1x2_away",
            projection_source="shots_on_away",
            explanation_template=f"Porque {away_name} proyecta mayor efectividad y precisión en remates dirigidos al arco.",
        ),
    ])

    # 5. Fueras de Juego Totales (Mínima informativa: +1.5)
    for line in [1.5, 2.5, 3.5, 4.5, 5.5]:
        catalog.append(
            MarketDefinition(
                id=f"offsides_total_over_{int(line*10)}",
                category="Fueras de juego",
                group="offsides_total",
                selection_template=f"Más de {line} fueras de juego",
                market_template="Fueras de juego totales",
                line=line,
                side="over",
                probability_source="neg_bin_offsides_total",
                projection_source="total_offsides",
                explanation_template="Porque el modelo proyecta {projection:.2f} fueras de juego totales.",
            )
        )
    for line in [2.5, 3.5, 4.5]:
        catalog.append(
            MarketDefinition(
                id=f"offsides_total_under_{int(line*10)}",
                category="Fueras de juego",
                group="offsides_total",
                selection_template=f"Menos de {line} fueras de juego",
                market_template="Fueras de juego totales",
                line=line,
                side="under",
                probability_source="neg_bin_offsides_total",
                projection_source="total_offsides",
                explanation_template="Porque el modelo proyecta {projection:.2f} fueras de juego totales.",
            )
        )

    # Fueras de Juego de Equipo (Mínima informativa: +0.5)
    for team_prefix, team_name, prob_src, proj_src in [
        ("offsides_home", home_name, "neg_bin_offsides_home", "offsides_home"),
        ("offsides_away", away_name, "neg_bin_offsides_away", "offsides_away"),
    ]:
        for line in [0.5, 1.5, 2.5, 3.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Fueras de juego",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} fueras de juego",
                    market_template=f"Fueras de juego de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} fueras de juego para {team_name}.",
                )
            )
        for line in [1.5, 2.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Fueras de juego",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} fueras de juego",
                    market_template=f"Fueras de juego de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} fueras de juego para {team_name}.",
                )
            )

    # 6. Goles Totales (Mínima informativa: +0.5)
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        catalog.append(
            MarketDefinition(
                id=f"goals_total_over_{int(line*10)}",
                category="Goles",
                group="total_goals",
                selection_template=f"Más de {line} goles",
                market_template="Goles totales",
                line=line,
                side="over",
                probability_source="matrix_goals_total",
                projection_source="total_goals",
                explanation_template="Porque la expectativa conjunta es de {projection:.2f} goles.",
            )
        )
    for line in [1.5, 2.5, 3.5, 4.5]:
        catalog.append(
            MarketDefinition(
                id=f"goals_total_under_{int(line*10)}",
                category="Goles",
                group="total_goals",
                selection_template=f"Menos de {line} goles",
                market_template="Goles totales",
                line=line,
                side="under",
                probability_source="matrix_goals_total",
                projection_source="total_goals",
                explanation_template="Porque la expectativa conjunta se proyecta en {projection:.2f} goles.",
            )
        )

    # Ambos equipos marcan
    catalog.append(
        MarketDefinition(
            id="btts_yes",
            category="Goles",
            group="both_score",
            selection_template="Sí",
            market_template="Ambos equipos marcan",
            line=None,
            side="binary",
            probability_source="btts_yes",
            projection_source=None,
            explanation_template="Porque la proyección de ambos anotando alcanza solidez estadística.",
        )
    )
    catalog.append(
        MarketDefinition(
            id="btts_no",
            category="Goles",
            group="both_score",
            selection_template="No (BTTS No)",
            market_template="Ambos equipos marcan",
            line=None,
            side="binary",
            probability_source="btts_no",
            projection_source=None,
            explanation_template="Porque al menos una de las ofensivas presenta baja probabilidad de romper el cero.",
        )
    )

    # Goles por Equipo (Mínima informativa: +0.5)
    for team_prefix, team_name, prob_src, proj_src in [
        ("home_goals", home_name, "matrix_home_goals", "expected_home_goals"),
        ("away_goals", away_name, "matrix_away_goals", "expected_away_goals"),
    ]:
        for line in [0.5, 1.5, 2.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Goles",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} goles",
                    market_template=f"Goles de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} goles para {team_name}.",
                )
            )
        for line in [1.5, 2.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Goles",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} goles",
                    market_template=f"Goles de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque el modelo proyecta {{projection:.2f}} goles para {team_name}.",
                )
            )

    # Portería a cero
    catalog.append(
        MarketDefinition(
            id="clean_sheet_home",
            category="Goles",
            group="clean_sheet",
            selection_template=f"{home_name} no recibe gol",
            market_template=f"Portería a cero de {home_name}",
            line=None,
            side="binary",
            probability_source="clean_sheet_home",
            projection_source=None,
            explanation_template=f"Porque el modelo proyecta solidez defensiva para {home_name}.",
        )
    )
    catalog.append(
        MarketDefinition(
            id="clean_sheet_away",
            category="Goles",
            group="clean_sheet",
            selection_template=f"{away_name} no recibe gol",
            market_template=f"Portería a cero de {away_name}",
            line=None,
            side="binary",
            probability_source="clean_sheet_away",
            projection_source=None,
            explanation_template=f"Porque el modelo proyecta solidez defensiva para {away_name}.",
        )
    )

    # 7. Mercados por Mitad
    catalog.extend([
        MarketDefinition(
            id="first_half_over_05",
            category="Mitades",
            group="first_half",
            selection_template="1T Más de 0.5 goles",
            market_template="Primer tiempo",
            line=0.5,
            side="over",
            probability_source="first_half_over_05",
            projection_source=None,
            explanation_template="Porque la intensidad proyectada en la primera mitad favorece goles tempranos.",
        ),
        MarketDefinition(
            id="first_half_under_15",
            category="Mitades",
            group="first_half",
            selection_template="1T Menos de 1.5 goles",
            market_template="Primer tiempo",
            line=1.5,
            side="under",
            probability_source="first_half_under_15",
            projection_source=None,
            explanation_template="Porque los planteos tácticos iniciales prevén un desarrollo controlado en la primera parte.",
        ),
        MarketDefinition(
            id="first_half_over_15",
            category="Mitades",
            group="first_half",
            selection_template="1T Más de 1.5 goles",
            market_template="Primer tiempo",
            line=1.5,
            side="over",
            probability_source="first_half_over_15",
            projection_source=None,
            explanation_template="Porque el ritmo temprano anticipa múltiples ocasiones en la primera etapa.",
        ),
        MarketDefinition(
            id="second_half_over_05",
            category="Mitades",
            group="second_half",
            selection_template="2T Más de 0.5 goles",
            market_template="Segundo tiempo",
            line=0.5,
            side="over",
            probability_source="second_half_over_05",
            projection_source=None,
            explanation_template="Porque el desgaste físico y los ajustes tácticos abren los espacios en el segundo tiempo.",
        ),
        MarketDefinition(
            id="second_half_under_15",
            category="Mitades",
            group="second_half",
            selection_template="2T Menos de 1.5 goles",
            market_template="Segundo tiempo",
            line=1.5,
            side="under",
            probability_source="second_half_under_15",
            projection_source=None,
            explanation_template="Porque se anticipa un cierre defensivo y disputado en la etapa final.",
        ),
        MarketDefinition(
            id="second_half_over_15",
            category="Mitades",
            group="second_half",
            selection_template="2T Más de 1.5 goles",
            market_template="Segundo tiempo",
            line=1.5,
            side="over",
            probability_source="second_half_over_15",
            projection_source=None,
            explanation_template="Porque el volumen ofensivo suele incrementarse hacia el tramo final.",
        ),
        MarketDefinition(
            id="goal_both_halves",
            category="Mitades",
            group="goal_both_halves",
            selection_template="Habrá gol en ambas mitades",
            market_template="Gol en ambas mitades",
            line=None,
            side="binary",
            probability_source="goal_both_halves",
            projection_source="total_goals",
            explanation_template="Porque la intensidad de ambos clubes proyecta presencia de gol tanto en el 1T como en el 2T.",
        ),
        MarketDefinition(
            id="team_score_both_halves_home",
            category="Mitades",
            group="team_score_both_halves",
            selection_template=f"{home_name} anota en ambas mitades",
            market_template=f"{home_name} anota en ambas mitades",
            line=None,
            side="binary",
            probability_source="team_score_both_halves_home",
            projection_source="expected_home_goals",
            explanation_template=f"Porque la alta productividad ofensiva de {home_name} se distribuye con solvencia en ambos tiempos.",
        ),
        MarketDefinition(
            id="team_score_both_halves_away",
            category="Mitades",
            group="team_score_both_halves",
            selection_template=f"{away_name} anota en ambas mitades",
            market_template=f"{away_name} anota en ambas mitades",
            line=None,
            side="binary",
            probability_source="team_score_both_halves_away",
            projection_source="expected_away_goals",
            explanation_template=f"Porque {away_name} cuenta con la eficacia para vulnerar la portería rival en ambas mitades.",
        ),
    ])

    # 8. Resultado del Partido (1X2, Doble Oportunidad, DNB, Gana a Cero)
    catalog.extend([
        MarketDefinition(
            id="match_1x2_home",
            category="Resultado",
            group="1x2",
            selection_template=home_name,
            market_template="Resultado del partido",
            line=None,
            side="1x2",
            probability_source="match_1x2_home",
            projection_source="expected_home_goals",
            explanation_template=f"Porque el modelo otorga clara ventaja posicional a {home_name}.",
        ),
        MarketDefinition(
            id="match_1x2_draw",
            category="Resultado",
            group="1x2",
            selection_template="Empate",
            market_template="Resultado del partido",
            line=None,
            side="1x2",
            probability_source="match_1x2_draw",
            projection_source=None,
            explanation_template="Porque la paridad de fuerzas tácticas anticipa equilibrio en el marcador.",
        ),
        MarketDefinition(
            id="match_1x2_away",
            category="Resultado",
            group="1x2",
            selection_template=away_name,
            market_template="Resultado del partido",
            line=None,
            side="1x2",
            probability_source="match_1x2_away",
            projection_source="expected_away_goals",
            explanation_template=f"Porque el modelo otorga ventaja en rendimiento a {away_name}.",
        ),
        MarketDefinition(
            id="double_chance_1x",
            category="Resultado",
            group="double_chance",
            selection_template=f"{home_name} o Empate (1X)",
            market_template="Doble oportunidad",
            line=None,
            side="binary",
            probability_source="double_chance_1x",
            projection_source=None,
            explanation_template=f"Porque la fortaleza de {home_name} en su campo reduce la probabilidad de derrota visitante.",
        ),
        MarketDefinition(
            id="double_chance_x2",
            category="Resultado",
            group="double_chance",
            selection_template=f"{away_name} o Empate (X2)",
            market_template="Doble oportunidad",
            line=None,
            side="binary",
            probability_source="double_chance_x2",
            projection_source=None,
            explanation_template=f"Porque el rendimiento de {away_name} respalda sumar al menos un punto.",
        ),
        MarketDefinition(
            id="double_chance_12",
            category="Resultado",
            group="double_chance",
            selection_template=f"{home_name} o {away_name} (12)",
            market_template="Doble oportunidad",
            line=None,
            side="binary",
            probability_source="double_chance_12",
            projection_source=None,
            explanation_template="Porque ambos equipos tienen vocación ofensiva, reduciendo la probabilidad de empate.",
        ),
        MarketDefinition(
            id="dnb_home",
            category="Resultado",
            group="dnb",
            selection_template=f"DNB {home_name}",
            market_template="Empate apuesta no válida",
            line=None,
            side="binary",
            probability_source="dnb_home",
            projection_source=None,
            explanation_template=f"Porque ante un eventual empate la apuesta se protege respaldando la victoria de {home_name}.",
        ),
        MarketDefinition(
            id="dnb_away",
            category="Resultado",
            group="dnb",
            selection_template=f"DNB {away_name}",
            market_template="Empate apuesta no válida",
            line=None,
            side="binary",
            probability_source="dnb_away",
            projection_source=None,
            explanation_template=f"Porque ante un eventual empate la apuesta se protege respaldando la victoria de {away_name}.",
        ),
        MarketDefinition(
            id="win_to_nil_home",
            category="Resultado",
            group="win_to_nil",
            selection_template=f"{home_name} gana a cero",
            market_template="Gana a cero",
            line=None,
            side="binary",
            probability_source="win_to_nil_home",
            projection_source=None,
            explanation_template=f"Porque se conjuga la victoria de {home_name} con solidez en su propia portería.",
        ),
        MarketDefinition(
            id="win_to_nil_away",
            category="Resultado",
            group="win_to_nil",
            selection_template=f"{away_name} gana a cero",
            market_template="Gana a cero",
            line=None,
            side="binary",
            probability_source="win_to_nil_away",
            projection_source=None,
            explanation_template=f"Porque se conjuga la victoria de {away_name} con solidez en su propia portería.",
        ),
    ])

    # Combinadas de Partido (Combos de Resultado y Goles derivados de Dixon-Coles)
    catalog.extend([
        MarketDefinition(
            id="combo_1x_over_15",
            category="Resultado",
            group="combo_result_goals",
            selection_template=f"{home_name} o Empate (1X) y Más de 1.5 goles",
            market_template="Combinada Doble Oportunidad y Total de Goles",
            line=1.5,
            side="binary",
            probability_source="combo_1x_over_15",
            projection_source="total_goals",
            explanation_template=f"Porque se combina la fortaleza de {home_name} de local con una expectativa conjunta superior a 1.5 goles.",
        ),
        MarketDefinition(
            id="combo_x2_over_15",
            category="Resultado",
            group="combo_result_goals",
            selection_template=f"{away_name} o Empate (X2) y Más de 1.5 goles",
            market_template="Combinada Doble Oportunidad y Total de Goles",
            line=1.5,
            side="binary",
            probability_source="combo_x2_over_15",
            projection_source="total_goals",
            explanation_template=f"Porque {away_name} suma puntos en un trámite que garantiza un mínimo de 2 goles totales.",
        ),
        MarketDefinition(
            id="combo_1x_under_35",
            category="Resultado",
            group="combo_result_goals",
            selection_template=f"{home_name} o Empate (1X) y Menos de 3.5 goles",
            market_template="Combinada Doble Oportunidad y Total de Goles",
            line=3.5,
            side="binary",
            probability_source="combo_1x_under_35",
            projection_source="total_goals",
            explanation_template=f"Porque {home_name} controla el ritmo en su estadio manteniendo el partido por debajo de 4 goles.",
        ),
        MarketDefinition(
            id="combo_x2_under_35",
            category="Resultado",
            group="combo_result_goals",
            selection_template=f"{away_name} o Empate (X2) y Menos de 3.5 goles",
            market_template="Combinada Doble Oportunidad y Total de Goles",
            line=3.5,
            side="binary",
            probability_source="combo_x2_under_35",
            projection_source="total_goals",
            explanation_template=f"Porque {away_name} rescata unidades en un contexto defensivo y cerrado.",
        ),
        MarketDefinition(
            id="combo_1_over_15",
            category="Resultado",
            group="combo_result_goals",
            selection_template=f"{home_name} gana y Más de 1.5 goles",
            market_template="Combinada Ganador y Total de Goles",
            line=1.5,
            side="binary",
            probability_source="combo_1_over_15",
            projection_source="expected_home_goals",
            explanation_template=f"Porque el triunfo proyectado de {home_name} viene acompañado de solvencia goleadora.",
        ),
        MarketDefinition(
            id="combo_2_over_15",
            category="Resultado",
            group="combo_result_goals",
            selection_template=f"{away_name} gana y Más de 1.5 goles",
            market_template="Combinada Ganador y Total de Goles",
            line=1.5,
            side="binary",
            probability_source="combo_2_over_15",
            projection_source="expected_away_goals",
            explanation_template=f"Porque el triunfo visitante de {away_name} se sustenta en superar la barrera del 1.5 goles.",
        ),
        MarketDefinition(
            id="combo_btts_over_25",
            category="Goles",
            group="combo_result_goals",
            selection_template="Ambos marcan y Más de 2.5 goles",
            market_template="Combinada Ambos Marcan y Total de Goles",
            line=2.5,
            side="binary",
            probability_source="combo_btts_over_25",
            projection_source="total_goals",
            explanation_template="Porque la paridad ofensiva y debilidades defensivas anticipan goles mutuos y marcador abultado.",
        ),
    ])

    # 9. Especiales
    catalog.append(
        MarketDefinition(
            id="hit_woodwork",
            category="Especiales",
            group="woodwork",
            selection_template="Tiro al palo en el partido",
            market_template="Tiros al palo",
            line=0.5,
            side="binary",
            probability_source="hit_woodwork",
            projection_source="tot_woodwork",
            explanation_template="Porque ambos equipos registran una alta frecuencia de remates a los postes.",
        )
    )

    # 10. Multigoles (Rango de Goles)
    for multigoal_id, label, prob_src in [
        ("multigoal_1_3", "1 a 3 goles", "multigoal_1_3"),
        ("multigoal_2_4", "2 a 4 goles", "multigoal_2_4"),
        ("multigoal_2_5", "2 a 5 goles", "multigoal_2_5"),
    ]:
        catalog.append(
            MarketDefinition(
                id=multigoal_id,
                category="Goles",
                group="multigoals",
                selection_template=label,
                market_template="Multigoles",
                line=None,
                side="binary",
                probability_source=prob_src,
                projection_source="total_goals",
                explanation_template=f"Porque el modelo proyecta un volumen de {{projection:.2f}} goles enmarcados en el rango de {label}.",
            )
        )

    # 11. Combos 1X2 + Ambos Marcan (BTTS)
    catalog.extend([
        MarketDefinition(
            id="combo_1_btts",
            category="Resultado",
            group="combo_1x2_btts",
            selection_template=f"{home_name} gana y Ambos Marcan",
            market_template="Ganador y Ambos Marcan",
            line=None,
            side="binary",
            probability_source="combo_1_btts",
            projection_source="expected_home_goals",
            explanation_template=f"Porque proyecta victoria de {home_name} con vulnerabilidad defensiva mutua.",
        ),
        MarketDefinition(
            id="combo_2_btts",
            category="Resultado",
            group="combo_1x2_btts",
            selection_template=f"{away_name} gana y Ambos Marcan",
            market_template="Ganador y Ambos Marcan",
            line=None,
            side="binary",
            probability_source="combo_2_btts",
            projection_source="expected_away_goals",
            explanation_template=f"Porque proyecta victoria de {away_name} con goles en ambas porterías.",
        ),
        MarketDefinition(
            id="combo_1x_btts",
            category="Resultado",
            group="combo_1x2_btts",
            selection_template=f"{home_name} o Empate (1X) y Ambos Marcan",
            market_template="Doble Oportunidad y Ambos Marcan",
            line=None,
            side="binary",
            probability_source="combo_1x_btts",
            projection_source="expected_home_goals",
            explanation_template=f"Porque {home_name} asegura puntos en un duelo con anotaciones de ambos bandos.",
        ),
        MarketDefinition(
            id="combo_x2_btts",
            category="Resultado",
            group="combo_1x2_btts",
            selection_template=f"{away_name} o Empate (X2) y Ambos Marcan",
            market_template="Doble Oportunidad y Ambos Marcan",
            line=None,
            side="binary",
            probability_source="combo_x2_btts",
            projection_source="expected_away_goals",
            explanation_template=f"Porque {away_name} rescata puntos en un trámite de ida y vuelta con goles mutuos.",
        ),
    ])

    # 12. Ambos Marcan en el 2do Tiempo (BTTS 2T)
    catalog.append(
        MarketDefinition(
            id="btts_second_half",
            category="Mitades",
            group="btts_second_half",
            selection_template="Ambos marcan en el 2T",
            market_template="Ambos equipos anotan en el 2do tiempo",
            line=None,
            side="binary",
            probability_source="btts_second_half",
            projection_source=None,
            explanation_template="Porque la intensidad y desgaste físico en la segunda mitad abren espacios para goles mutuos.",
        )
    )

    # 13. Córners 1er Tiempo (1T)
    for line in [3.5, 4.5]:
        catalog.append(
            MarketDefinition(
                id=f"corners_1h_over_{int(line*10)}",
                category="Córners",
                group="corners_first_half",
                selection_template=f"1T Más de {line} córners",
                market_template="Córners en el 1er tiempo",
                line=line,
                side="over",
                probability_source="neg_bin_corners_1h",
                projection_source="corners_first_half",
                explanation_template="Porque el modelo proyecta {projection:.2f} córners en la etapa inicial.",
            )
        )
    for line in [4.5, 5.5]:
        catalog.append(
            MarketDefinition(
                id=f"corners_1h_under_{int(line*10)}",
                category="Córners",
                group="corners_first_half",
                selection_template=f"1T Menos de {line} córners",
                market_template="Córners en el 1er tiempo",
                line=line,
                side="under",
                probability_source="neg_bin_corners_1h",
                projection_source="corners_first_half",
                explanation_template="Porque se anticipa un inicio cauteloso con {projection:.2f} córners esperados en el 1T.",
            )
        )

    # 14. Faltas Cometidas
    for line in [21.5, 23.5, 25.5, 27.5]:
        catalog.append(
            MarketDefinition(
                id=f"fouls_total_over_{int(line*10)}",
                category="Faltas",
                group="fouls_total",
                selection_template=f"Más de {line} faltas",
                market_template="Faltas totales",
                line=line,
                side="over",
                probability_source="neg_bin_fouls_total",
                projection_source="total_fouls",
                explanation_template="Porque el modelo proyecta un partido trabado con {projection:.1f} infracciones estimadas.",
            )
        )
    for line in [23.5, 25.5, 27.5]:
        catalog.append(
            MarketDefinition(
                id=f"fouls_total_under_{int(line*10)}",
                category="Faltas",
                group="fouls_total",
                selection_template=f"Menos de {line} faltas",
                market_template="Faltas totales",
                line=line,
                side="under",
                probability_source="neg_bin_fouls_total",
                projection_source="total_fouls",
                explanation_template="Porque se proyecta un duelo de ritmo limpio con {projection:.1f} faltas estimadas.",
            )
        )
    for team_prefix, team_name, prob_src, proj_src in [
        ("fouls_home", home_name, "neg_bin_fouls_home", "fouls_home"),
        ("fouls_away", away_name, "neg_bin_fouls_away", "fouls_away"),
    ]:
        for line in [10.5, 11.5, 12.5, 13.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_over_{int(line*10)}",
                    category="Faltas",
                    group=team_prefix,
                    selection_template=f"{team_name} Más de {line} faltas",
                    market_template=f"Faltas de {team_name}",
                    line=line,
                    side="over",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque {team_name} proyecta cometer {{projection:.1f}} faltas.",
                )
            )
        for line in [10.5, 11.5, 12.5]:
            catalog.append(
                MarketDefinition(
                    id=f"{team_prefix}_under_{int(line*10)}",
                    category="Faltas",
                    group=team_prefix,
                    selection_template=f"{team_name} Menos de {line} faltas",
                    market_template=f"Faltas de {team_name}",
                    line=line,
                    side="under",
                    probability_source=prob_src,
                    projection_source=proj_src,
                    explanation_template=f"Porque {team_name} mantiene un esquema disciplinado con {{projection:.1f}} faltas proyectadas.",
                )
            )
    catalog.extend([
        MarketDefinition(
            id="fouls_1x2_home",
            category="Faltas",
            group="fouls_1x2",
            selection_template=f"{home_name} comete más faltas",
            market_template="Más faltas cometidas",
            line=None,
            side="binary",
            probability_source="fouls_1x2_home",
            projection_source="fouls_home",
            explanation_template=f"Porque {home_name} presenta mayor fricción defensiva.",
        ),
        MarketDefinition(
            id="fouls_1x2_away",
            category="Faltas",
            group="fouls_1x2",
            selection_template=f"{away_name} comete más faltas",
            market_template="Más faltas cometidas",
            line=None,
            side="binary",
            probability_source="fouls_1x2_away",
            projection_source="fouls_away",
            explanation_template=f"Porque {away_name} suele cortar más el juego como visitante.",
        ),
    ])

    return catalog
