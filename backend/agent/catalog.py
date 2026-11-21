"""What the agent can ask about: the metrics of the GI index, and the microzones.

Only metrics listed here can reach a query, so the catalog is also the
allow-list of columns. Built once at startup from the DuckDB columns and the
notebook's metadata.json, so a new export with fewer columns still works.
"""

import difflib
import json
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.database import Database


class Kind(StrEnum):
    SCORE = "score"  # 0-1 in the data, shown as 0-100 like the app does
    RAW = "raw"  # a measured value with its own unit


class Agg(StrEnum):
    AVG = "avg"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    description: str
    group: str
    kind: Kind
    unit: str = ""
    agg: Agg = Agg.AVG  # how hexes add up to a microzone
    derived: bool = False  # computed from the weights, not a column

    @property
    def is_score(self) -> bool:
        return self.kind is Kind.SCORE

    @property
    def scale(self) -> float:
        """Stored values times this are what people see: scores 0-100, shares in %."""
        return 100.0 if self.is_score or self.unit == "%" else 1.0

    @property
    def shown_unit(self) -> str:
        return "/100" if self.is_score else self.unit


# Scores the user's weights change: the same formula as frontend/js/scoring/score.js.
DERIVED = (
    Metric(
        "score",
        "Green infrastructure need (map score)",
        "The score on the app's map and ranking: GI need with the chosen weights, "
        "times space to build when only_buildable is on. Higher = greening helps more.",
        "score",
        Kind.SCORE,
        derived=True,
    ),
    Metric(
        "need",
        "GI need",
        "Heat & people exposed ^ w_he x vulnerable groups ^ w_v x lack of green ^ w_gd "
        "(INFORM-style geometric mean), ignoring space to build.",
        "score",
        Kind.SCORE,
        derived=True,
    ),
    Metric(
        "priority",
        "GI priority",
        "GI need x space to build: high where need is high and there is room to act.",
        "score",
        Kind.SCORE,
        derived=True,
    ),
)

DIMENSIONS = (
    Metric(
        "he",
        "Heat & people exposed",
        "Heat hazard combined with how many people live or spend the day there.",
        "dimension",
        Kind.SCORE,
    ),
    Metric(
        "v",
        "Vulnerable groups",
        "Older residents (65+, 75+), young children (0-4), schools, kindergartens and doctors.",
        "dimension",
        Kind.SCORE,
    ),
    Metric(
        "gd",
        "Lack of green",
        "Little green vegetation or tree cover, much sealed ground, or far to the nearest green area.",
        "dimension",
        Kind.SCORE,
    ),
    Metric(
        "feas",
        "Space to build",
        "Feasibility: brownfields, vacant land, parking, cycle and street corridors.",
        "dimension",
        Kind.SCORE,
    ),
)

COMPONENTS = {
    "c_heat": ("Heat hazard", "Heatwave day and night air temperature and surface temperature."),
    "c_exposure_day": ("Daytime exposure", "People present during the day per hectare."),
    "c_exposure_night": ("Night-time exposure", "Residents per hectare."),
    "c_exposure": ("Exposure", "Day and night exposure combined."),
    "c_vulnerability": (
        "Vulnerability",
        "Older residents, young children and sensitive facilities.",
    ),
    "c_green_supply": (
        "Green supply deficit",
        "Little green vegetation (Sentinel-2 NDVI), green share, tree cover and green per person; "
        "high sealing.",
    ),
    "c_green_access": (
        "Green access deficit",
        "Distance to the nearest green area of 0.5 ha or more.",
    ),
    "c_opportunity": ("Opportunity", "Brownfields, vacant land and parking that could be greened."),
    "c_corridors": ("Corridors", "Cycle paths and streets that could carry green corridors."),
    "c_buildings": ("Buildings", "Building energy data (not available yet)."),
    "d_heat_exposure": ("Heat & exposure dimension (notebook)", "As computed in the notebook."),
    "d_vulnerability": ("Vulnerability dimension (notebook)", "As computed in the notebook."),
    "d_green_deficit": ("Green deficit dimension (notebook)", "As computed in the notebook."),
    "d_feasibility": ("Feasibility dimension (notebook)", "As computed in the notebook."),
    "gi_need_provisional": (
        "GI need, balanced weights (notebook)",
        "The notebook's need with equal weights.",
    ),
    "gi_priority_provisional": (
        "GI priority, balanced weights (notebook)",
        "The notebook's need x feasibility.",
    ),
}

# raw_* columns: (label, unit, how hexes add up to a microzone)
RAW = {
    "raw_heatwave_tmax": ("Heatwave daytime max temperature", "°C", Agg.AVG),
    "raw_heatwave_tmin": ("Heatwave night-time min temperature", "°C", Agg.AVG),
    "raw_lst_microzone": ("Land surface temperature (microzone mean)", "°C", Agg.AVG),
    "raw_residents": ("Residents", "people", Agg.SUM),
    "raw_day_people": ("People present during the day", "people", Agg.SUM),
    "raw_res_density": ("Residents per hectare", "people/ha", Agg.AVG),
    "raw_day_density": ("Daytime people per hectare", "people/ha", Agg.AVG),
    "raw_share_65plus": ("Share of residents aged 65+", "%", Agg.AVG),
    "raw_share_75plus": ("Share of residents aged 75+", "%", Agg.AVG),
    "raw_share_0_4": ("Share of children aged 0-4", "%", Agg.AVG),
    "raw_sensitive_facilities": ("Kindergartens, schools and doctors", "count", Agg.SUM),
    "raw_vegetation_share": (
        "Green vegetation: share with dense vegetation (Sentinel-2 NDVI >= 0.5, summer 2026)",
        "%",
        Agg.AVG,
    ),
    "raw_ndvi_mean": ("Mean NDVI (Sentinel-2, summer 2026, -1 to 1)", "", Agg.AVG),
    "raw_green_share": ("Share of area that is green", "%", Agg.AVG),
    "raw_tree_cover": ("Tree cover density", "%", Agg.AVG),
    "raw_sealing": ("Sealed ground (imperviousness)", "%", Agg.AVG),
    "raw_green_per_capita": ("Green area per resident", "m²/person", Agg.AVG),
    "raw_dist_green": (
        "Walking distance along streets to the nearest park or forest (0.5 ha+)",
        "m",
        Agg.AVG,
    ),
    "raw_brownfield_share": ("Share of area that is brownfield", "%", Agg.AVG),
    "raw_vacant_share": ("Share of area that is vacant land", "%", Agg.AVG),
    "raw_constraint_share": (
        "Share of area under constraints (roads, rail, water...)",
        "%",
        Agg.AVG,
    ),
    "raw_public_building_share": (
        "Share of area covered by public buildings (schools, offices, hospitals, sports halls)",
        "%",
        Agg.AVG,
    ),
    "raw_public_roof_m2": ("Public building footprint (roof) area", "m²", Agg.SUM),
    "raw_parking": ("Parking spaces", "spaces", Agg.SUM),
    "raw_cycle_density": ("Cycle path density", "", Agg.AVG),
    "raw_street_density": ("Street density (OpenStreetMap streets)", "m/ha", Agg.AVG),
}

# val_* columns: residents' 2020 heat survey, used to check the index.
# NOT part of any score. (label, unit, how hexes add up, description)
VALIDATION = {
    "val_perceived_heat": (
        "Share of residents' marks saying uncomfortable on hot days (2020 survey)",
        "%",
        Agg.AVG,
        "Not part of the score; supporting evidence only. Empty where a place has fewer "
        "than 3 marks.",
    ),
    "val_uncomfortable": (
        "Residents' marks: uncomfortable on hot days (2020 survey)",
        "marks",
        Agg.SUM,
        "Not part of the score.",
    ),
    "val_comfortable": (
        "Residents' marks: comfortable on hot days (2020 survey)",
        "marks",
        Agg.SUM,
        "Not part of the score.",
    ),
}

OTHER = {
    "area_ha": ("Hexagon area inside the city", "ha", Agg.SUM),
    "coverage": ("Share of the hexagon inside the study area", "%", Agg.AVG),
}


@dataclass(frozen=True)
class AgentContext:
    metrics: dict[str, Metric]
    microzones: tuple[str, ...]
    hex_count: int
    metadata: dict[str, Any]

    def metric(self, name: str) -> Metric:
        from agent.query import ToolError  # avoid an import cycle

        metric = self.metrics.get(name)
        if metric is None:
            close = difflib.get_close_matches(name, list(self.metrics), n=3, cutoff=0.5)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            raise ToolError(f"unknown metric {name!r}{hint}")
        return metric

    def microzone(self, name: str) -> str:
        """The exact microzone name for what the user typed ("Losov" -> "Mikrozóna Lošov")."""
        from agent.query import ToolError

        wanted = _plain(name)
        by_plain = {_plain(z): z for z in self.microzones}
        if wanted in by_plain:
            return by_plain[wanted]
        partial = [z for p, z in by_plain.items() if wanted and wanted in p]
        if len(partial) == 1:
            return partial[0]
        close = partial or [
            by_plain[p] for p in difflib.get_close_matches(wanted, list(by_plain), n=3, cutoff=0.6)
        ]
        hint = f"; did you mean {', '.join(repr(z) for z in close[:5])}?" if close else ""
        raise ToolError(f"no microzone matches {name!r}{hint}")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = " ".join(text.replace("-", " ").split())
    return text.removeprefix("mikrozona ").strip()


def build_context(db: Database) -> AgentContext:
    rows = db.query_sync("SELECT doc FROM metadata").rows
    metadata = json.loads(rows[0]["doc"]) if rows and rows[0]["doc"] else {}
    hex_count = db.query_sync("SELECT count(*) AS n FROM hexes").rows[0]["n"]
    # Columns with no values at all (c_buildings today) are left out.
    present = {
        c
        for c in db.hex_columns
        if db.query_sync(f'SELECT count("{c}") AS n FROM hexes').rows[0]["n"] > 0
    }
    indicators: dict[str, Any] = metadata.get("indicators") or {}

    metrics: list[Metric] = [*DERIVED]
    metrics += [m for m in DIMENSIONS if m.name in present]
    for name, (label, description) in COMPONENTS.items():
        if name in present:
            metrics.append(Metric(name, label, description, "component", Kind.SCORE))
    for name, (label, unit, agg) in RAW.items():
        if name in present:
            metrics.append(
                Metric(
                    name, label, _method(indicators.get(name[4:])), "indicator", Kind.RAW, unit, agg
                )
            )
    for name in sorted(present):
        if name.startswith("mu_"):
            raw_label = RAW.get("raw_" + name[3:], (name[3:],))[0]
            metrics.append(
                Metric(
                    name,
                    f"{raw_label} (0-100 score)",
                    f"The indicator {name[3:]} rescaled to 0-1 before it enters its component. "
                    + _method(indicators.get(name[3:])),
                    "indicator score",
                    Kind.SCORE,
                )
            )
    for name, (label, unit, agg, description) in VALIDATION.items():
        if name in present:
            metrics.append(Metric(name, label, description, "validation", Kind.RAW, unit, agg))
    for name, (label, unit, agg) in OTHER.items():
        if name in present:
            metrics.append(Metric(name, label, "", "other", Kind.RAW, unit, agg))

    return AgentContext(
        metrics={m.name: m for m in metrics},
        microzones=db.microzones,
        hex_count=int(hex_count),
        metadata=metadata,
    )


def _method(spec: dict[str, Any] | None) -> str:
    """How an indicator becomes a 0-1 score, from metadata.json."""
    if not spec:
        return ""
    params = spec.get("params_resolved") or {}
    low, high = params.get("low"), params.get("high")
    direction = "rises" if spec.get("function") == "linear_increasing" else "falls"
    text = f"Part of {spec.get('component')} (weight {spec.get('weight')})"
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        text += f"; its score {direction} linearly from {low:.4g} to {high:.4g}"
        if spec.get("log"):
            text += " (log scale)"
    return text + "."
