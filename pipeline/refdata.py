"""Method constants. We import them from the challenge's own `ccn_tools.factors` so our calculation and
the reference calculator share one source of truth (docs/METHODOLOGY.md documents every value).
`ccn_tools` is code shipped in the package, not data: importing it does not bypass the Raw stage."""
from __future__ import annotations

import sys

from .config import Config

_tools = str(Config().tools_dir)
if _tools not in sys.path:
    sys.path.insert(0, _tools)

from ccn_tools import factors as F  # noqa: E402
from ccn_tools import reference_calculator as reference_calculator  # noqa: E402,F401
from ccn_tools import score as ccn_score  # noqa: E402,F401

FX_PER_EUR = F.FX_PER_EUR

# Fuel net calorific values per native unit (METHODOLOGY.md §2, `energy` row).
NCV_PER_UNIT = {("lng", "t"): F.NCV["lng_t"], ("lpg", "t"): F.NCV["lpg_t"],
                ("light_fuel_oil", "l"): F.NCV["lfo_l"], ("diesel", "l"): F.NCV["diesel_l"],
                ("hvo", "l"): F.NCV["hvo_l"]}

FARM_CROP_BY_MATERIAL = {"M100": "turnip_rape", "M110": "pea", "M111": "potato", "M112": "carrot", "M113": "spinach"}

WASTE_EF_BY_TREATMENT = {"anaerobic_digestion": "EF-WASTE-BIO-AD", "composting": "EF-WASTE-BIO-COMPOST",
                         "incineration": "EF-WASTE-MIXED-INC", "recycling": "EF-WASTE-RECYCLE",
                         "landfill_codigestion": "EF-WASTE-SPENTEARTH"}

COMMUTE_MODES = ["car", "carpool", "bus", "train", "bike_walk", "ev_car"]
COMMUTE_WEEKS_PER_YEAR = 46

ORGANIC_SOIL_THRESHOLD = 0.30  # docs/TASKS_AND_SCORING.md, A1 `soil_misreport`
