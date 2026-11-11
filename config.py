"""All fixed inputs and assumptions of SAYA in one place.

Every number below is a labelled assumption for the course demo, not a
measured fact. Change them here and rerun main.py to see the effect.
"""

from datetime import timedelta, timezone

# ---------------------------------------------------------------- area
# Walkable area between Astana IT University and Mega Silk Way (Astana, EXPO district).
AREA_CENTER = (51.0900, 71.4125)  # (lat, lon)
AREA_RADIUS_M = 700
PROJECTED_CRS = "EPSG:32642"  # UTM zone 42N, metres. Astana is at 71.4 deg E.

PLACES = {
    "aitu": ("Astana IT University", 51.0908607, 71.4184149),
    "megasilkway": ("Mega Silk Way", 51.089182, 71.406678),
}
DEFAULT_START = "aitu"
DEFAULT_END = "megasilkway"

ASTANA_TZ = timezone(timedelta(hours=5))  # Kazakhstan has used UTC+5 nationwide since March 2024
DEFAULT_DATE = "2026-07-15"  # a summer day, so the heat question matters
DEFAULT_TIME = "16:00"

# ---------------------------------------------------------------- shade
METERS_PER_LEVEL = 3.2          # building:levels -> height
DEFAULT_BUILDING_HEIGHT = 9.0   # used when OSM has neither height nor levels (about 3 floors)
MAX_SHADOW_LENGTH = 250.0       # cap for a very low sun, so shadows stay finite
TREE_CROWN_RADIUS_M = 3.0       # a tree or tree row shades this far around itself

# ---------------------------------------------------------------- search (A*)
# Edge cost = length * access_multiplier * (1 + sun_weight * sun_fraction) + crossing_extra_m.
# Multipliers are >= 1 and extras are >= 0, so straight-line distance never
# overestimates the cost, which keeps the A* heuristic admissible.
SUN_WEIGHT = {"shortest": 0.0, "shaded": 3.0}  # "shaded": 1 m in the sun feels like 4 m

FOOT_HIGHWAYS = {"footway", "pedestrian", "path", "living_street", "corridor"}
# Car roads with real traffic (driveways and parking lanes are "service" and count as quiet roads)
BUSY_ROADS = {"primary", "secondary", "tertiary", "unclassified", "trunk",
              "primary_link", "secondary_link", "tertiary_link", "trunk_link"}

# Mobility profiles. A multiplier of None means the profile cannot pass at all.
PROFILES = {
    "wheelchair": {
        "label": "Wheelchair user",
        "speed_mps": 0.9,
        "heat_vulnerability": 1.5,
        "road_no_sidewalk": 1.6,         # rolling along a quiet road or parking lane
        "busy_road": 3.0,                # rolling along a road with traffic
        "paving_stones": 1.2,            # bumpy surface
        "uncontrolled_crossing_m": 60,   # extra metres for a crossing without a traffic light
        "barrier": {"steps": None, "broken_ramp": None, "construction": None},
    },
    "elderly": {
        "label": "Elderly pedestrian",
        "speed_mps": 1.0,
        "heat_vulnerability": 1.8,
        "road_no_sidewalk": 1.4,
        "busy_road": 2.0,
        "paving_stones": 1.05,
        "uncontrolled_crossing_m": 40,
        "barrier": {"steps": 3.0, "broken_ramp": 1.0, "construction": None},
    },
    "standard": {
        "label": "Pedestrian without mobility needs",
        "speed_mps": 1.3,
        "heat_vulnerability": 1.0,
        "road_no_sidewalk": 1.1,
        "busy_road": 1.2,
        "paving_stones": 1.0,
        "uncontrolled_crossing_m": 0,
        "barrier": {"steps": 1.0, "broken_ramp": 1.0, "construction": None},
    },
}

# ---------------------------------------------------------------- Bayes
# Hypothesis: is it dangerously hot for walking right now?
# Prior P(Dangerous) by month (Astana climate, rough assumption).
HEAT_PRIOR_BY_MONTH = {6: 0.25, 7: 0.30, 8: 0.25, 5: 0.08, 9: 0.08}
HEAT_PRIOR_DEFAULT = 0.01

# Observation: the "feels like" temperature from the Open-Meteo forecast, in 3 buckets.
FEELS_LIKE_BUCKETS = [(24.0, "cool"), (30.0, "warm"), (float("inf"), "hot")]  # upper bounds, degC
# The forecast is a noisy sensor: P(reading bucket | true state)
HEAT_LIKELIHOOD = {
    "Dangerous": {"cool": 0.05, "warm": 0.25, "hot": 0.70},
    "Safe":      {"cool": 0.55, "warm": 0.35, "hot": 0.10},
}

# ---------------------------------------------------------------- MDP
MDP_GAMMA = 0.9
HEAT_STRESS_PENALTY = 60.0  # heat stress counts as bad as 60 extra minutes (many wheelchair users
                            # sweat less and overheat faster, so the penalty is high)
# Chance per minute in direct sun of becoming heat-stressed (before vulnerability multiplier)
HAZARD_PER_SUN_MINUTE = {"Dangerous": 0.03, "Safe": 0.002}
RECOVERY_IN_SHADE = 0.5  # P(recover) = 0.5 * shade fraction of the route, if already stressed
