"""
Vessel parameters (PDF objective: "collect and analyze ... vessel
parameters ...").

Each vessel type has the physical parameters that matter for routing:
  service_speed_kn : nominal calm-water speed
  length_m         : overall length (bigger ships ride waves better)
  draft_m          : how deep it sits (needs deeper water)
  wave_sensitivity : how strongly waves slow it (0 = tough, 1 = fragile)

These feed both the weather cost function and the ML speed model.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Vessel:
    name: str
    service_speed_kn: float
    length_m: float
    draft_m: float
    wave_sensitivity: float


VESSELS = {
    "Bulk Carrier (Panamax)":  Vessel("Bulk Carrier (Panamax)", 14.0, 229.0, 12.5, 0.75),
    "Container Ship":          Vessel("Container Ship",         22.0, 300.0, 14.5, 0.55),
    "Crude Oil Tanker (VLCC)": Vessel("Crude Oil Tanker (VLCC)", 16.0, 330.0, 20.5, 0.65),
    "General Cargo":           Vessel("General Cargo",          16.0, 150.0, 9.0,  0.85),
    "LNG Carrier":             Vessel("LNG Carrier",            19.0, 295.0, 12.0, 0.60),
}

DEFAULT_VESSEL = "Container Ship"


def vessel_list():
    return list(VESSELS.keys())


def get(name):
    return VESSELS[name]
