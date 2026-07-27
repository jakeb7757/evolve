from dataclasses import dataclass


SCHEMA_VERSION = "1.0"
SCORING_VERSION = "1.0"


@dataclass(frozen=True)
class NetworkConfig:
    key: str
    slug: str
    display_name: str | None = None
    short_name: str | None = None
    include_in_leaderboard: bool = True
    minimum_site_count: int | None = None
    notes: str = ""


INCLUDED_NETWORKS = (
    NetworkConfig("Tesla", "tesla-supercharger", "Tesla Supercharger", "Tesla"),
    NetworkConfig("Electrify America", "electrify-america"),
    NetworkConfig("eVgo Network", "evgo", "EVgo"),
    NetworkConfig("ChargePoint Network", "chargepoint", "ChargePoint"),
    NetworkConfig("IONNA", "ionna"),
    NetworkConfig("FCN", "francis-energy", "Francis Energy"),
    NetworkConfig("FLO", "flo"),
    NetworkConfig(
        "MERCEDES_BENZ",
        "mercedes-benz-high-power-charging",
        "Mercedes-Benz High-Power Charging",
        "Mercedes-Benz",
    ),
    NetworkConfig(
        "RIVIAN_ADVENTURE",
        "rivian-adventure-network",
        "Rivian Adventure Network",
        "Rivian",
        notes="Rivian Waypoints are intentionally excluded.",
    ),
    NetworkConfig("SHELL_RECHARGE", "shell-recharge", "Shell Recharge"),
    NetworkConfig("7CHARGE", "7charge", "7Charge"),
    NetworkConfig("FPLEV", "fpl-evolution", "FPL EVolution"),
    NetworkConfig("EVCS", "evcs"),
    NetworkConfig("RED_E", "red-e-charge", "Red E Charge"),
    NetworkConfig("WALMART", "walmart", "Walmart"),
)

NETWORK_CONFIG_BY_KEY = {network.key: network for network in INCLUDED_NETWORKS}

US_STATES_AND_DC = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    }
)

SCORING_CONFIG = {
    "weights": {
        "geographic_coverage": 0.25,
        "total_ports": 0.20,
        "average_site_size": 0.20,
        "large_site_share": 0.15,
        "high_power_share": 0.15,
        "connector_support": 0.05,
    },
    "thresholds": {
        "large_site_ports": 8,
        "high_power_kw": 150,
        "ultra_high_power_kw": 250,
        "minimum_scored_sites": 10,
        "average_site_size_target": 12,
        "power_confidence_target_percentage": 80,
        "meaningful_connector_share_percentage": 5,
        "meaningful_connector_count_cap": 25,
        "suspicious_site_decrease_percentage": 25,
    },
}

SITE_SIZE_BUCKETS = (
    ("1-2", "1–2 ports"),
    ("3-4", "3–4 ports"),
    ("5-7", "5–7 ports"),
    ("8-11", "8–11 ports"),
    ("12-19", "12–19 ports"),
    ("20+", "20+ ports"),
)

POWER_BUCKETS = (
    ("unknown", "Unknown"),
    ("below-50", "Below 50 kW"),
    ("50-149", "50–149 kW"),
    ("150-249", "150–249 kW"),
    ("250-349", "250–349 kW"),
    ("350+", "350+ kW"),
)


def validate_scoring_config() -> None:
    total = sum(SCORING_CONFIG["weights"].values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"Charging index scoring weights total {total}, not 1.0")
