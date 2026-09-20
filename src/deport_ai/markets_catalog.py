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

    return catalog
