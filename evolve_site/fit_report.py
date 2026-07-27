from decimal import Decimal, ROUND_HALF_UP


LEVEL_1_RATE_KW = Decimal("1.4")
LEVEL_2_RATE_KW = Decimal("7.2")
MONEY_PLACES = Decimal("0.01")
HOURS_PLACES = Decimal("0.1")


def _round_money(value):
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _round_hours(value):
    return value.quantize(HOURS_PLACES, rounding=ROUND_HALF_UP)


def _station_distance(station):
    try:
        return float(station.get("distance"))
    except (TypeError, ValueError):
        return float("inf")


def _network_names(stations):
    networks = {}
    for station in stations:
        network = str(station.get("ev_network") or "").strip()
        if network:
            networks.setdefault(network.casefold(), network)
    return sorted(networks.values(), key=str.casefold)


def build_fit_report(vehicle, cleaned_data, stations):
    """Combine cost, range, charging, and road coverage into one EV fit report."""
    location = cleaned_data["location"].strip()
    compact_location = location.replace("-", "")
    location_is_zip = compact_location.isdigit() and len(compact_location) in (5, 9)

    annual_miles = Decimal(cleaned_data["annual_miles"])
    daily_miles = Decimal(cleaned_data["daily_miles"])
    mpg = cleaned_data["mpg"]
    gas_price = cleaned_data["gas_price"]
    electricity_cost = cleaned_data["electricity_cost"]
    charging_hours = Decimal(cleaned_data["charging_hours"])
    reserve_percent = Decimal(cleaned_data["reserve_percent"])

    annual_gas_cost = (annual_miles / mpg) * gas_price
    annual_ev_energy = (
        annual_miles * vehicle.combined_kwh_per_100_miles / Decimal("100")
    )
    annual_electricity_cost = annual_ev_energy * electricity_cost
    annual_savings = annual_gas_cost - annual_electricity_cost
    monthly_savings = annual_savings / Decimal("12")

    daily_energy = (
        daily_miles * vehicle.combined_kwh_per_100_miles / Decimal("100")
    )
    level_1_hours = daily_energy / LEVEL_1_RATE_KW
    level_2_hours = daily_energy / LEVEL_2_RATE_KW
    level_1_fits = level_1_hours <= charging_hours
    level_2_fits = level_2_hours <= charging_hours

    if level_1_fits:
        charging_label = "Level 1 keeps up"
        charging_detail = (
            "A standard 120V outlet can replace your typical daily driving "
            "during the time you are parked."
        )
    elif level_2_fits:
        charging_label = "Level 2 recommended"
        charging_detail = (
            "A standard outlet falls behind, but a typical 7.2 kW Level 2 "
            "setup can replenish your daily driving overnight."
        )
    else:
        charging_label = "Charging window is tight"
        charging_detail = (
            "Even a typical 7.2 kW Level 2 setup may not fully replace your "
            "daily driving during the charging window entered."
        )

    epa_range = (
        Decimal(vehicle.epa_range_miles)
        if vehicle.epa_range_miles is not None
        else None
    )
    usable_range = None
    range_headroom = None
    range_fits = None
    range_days = None
    if epa_range is not None:
        usable_range = epa_range * (
            Decimal("1") - reserve_percent / Decimal("100")
        )
        range_headroom = usable_range - daily_miles
        range_fits = range_headroom >= 0
        range_days = usable_range / daily_miles

    if range_fits is True:
        range_label = "Comfortable daily range"
        range_detail = (
            f"After holding back a {int(reserve_percent)}% reserve, this EV "
            f"still has about {range_headroom.quantize(Decimal('1'))} miles "
            "beyond your typical day."
        )
    elif range_fits is False:
        range_label = "Daily range falls short"
        range_detail = (
            f"With a {int(reserve_percent)}% reserve, your typical day is "
            f"about {abs(range_headroom).quantize(Decimal('1'))} miles beyond "
            "the usable EPA range."
        )
    else:
        range_label = "EPA range unavailable"
        range_detail = (
            "FuelEconomy.gov does not publish an electric range for this "
            "specific vehicle configuration."
        )

    sorted_stations = sorted(stations, key=_station_distance)
    closest_station = sorted_stations[0] if sorted_stations else None
    closest_distance = (
        _station_distance(closest_station) if closest_station else None
    )
    if closest_distance == float("inf"):
        closest_distance = None

    if closest_station and closest_distance is not None:
        if closest_distance <= 10:
            coverage_label = "Strong fast-charging coverage"
        else:
            coverage_label = "Fast charging available nearby"
        coverage_detail = (
            f"{closest_station.get('station_name', 'The closest station')} is "
            f"about {closest_distance:.1f} miles away."
        )
    elif closest_station:
        coverage_label = "Fast charging found"
        coverage_detail = (
            "At least one qualifying station was returned, but its distance "
            "was not available."
        )
    else:
        coverage_label = "No nearby fast chargers found"
        coverage_detail = (
            "No public 80+ kW stations were returned for this location. The "
            "station service may also be temporarily unavailable."
        )

    if range_fits is False:
        verdict = {
            "tone": "caution",
            "label": "Look for more range",
            "summary": (
                "The ownership numbers may work, but this configuration does "
                "not preserve the range reserve you selected on a typical day."
            ),
        }
    elif not level_2_fits:
        verdict = {
            "tone": "caution",
            "label": "Charging window is tight",
            "summary": (
                "The EV covers the drive, but your overnight window may not "
                "replace the energy used each day."
            ),
        }
    elif level_1_fits and closest_station:
        verdict = {
            "tone": "excellent",
            "label": "Excellent fit",
            "summary": (
                "Your daily driving, home charging window, and nearby fast "
                "charging all line up well with this EV."
            ),
        }
    elif level_2_fits and closest_station:
        verdict = {
            "tone": "strong",
            "label": "Strong fit with Level 2",
            "summary": (
                "This EV fits your driving and road-charging needs, with "
                "Level 2 charging recommended at home."
            ),
        }
    elif level_1_fits:
        verdict = {
            "tone": "strong",
            "label": "Good fit at home",
            "summary": (
                "Your routine works well with this EV at home. Confirm fast "
                "charging along the longer trips you take regularly."
            ),
        }
    else:
        verdict = {
            "tone": "strong",
            "label": "Good fit with Level 2",
            "summary": (
                "The EV fits your routine with Level 2 home charging. Confirm "
                "fast charging along the longer trips you take regularly."
            ),
        }

    networks = _network_names(stations)

    return {
        "vehicle": vehicle,
        "location": location,
        "station_search_type": "zip" if location_is_zip else "city",
        "station_search_parameter": "zip_code" if location_is_zip else "city_state",
        "verdict": verdict,
        "annual_gas_cost": _round_money(annual_gas_cost),
        "annual_electricity_cost": _round_money(annual_electricity_cost),
        "annual_savings": _round_money(annual_savings),
        "monthly_savings": _round_money(monthly_savings),
        "monthly_difference": _round_money(abs(monthly_savings)),
        "five_year_savings": _round_money(annual_savings * Decimal("5")),
        "saves_money": annual_savings >= 0,
        "annual_ev_energy": annual_ev_energy.quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ),
        "daily_energy": daily_energy.quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        ),
        "level_1_hours": _round_hours(level_1_hours),
        "level_2_hours": _round_hours(level_2_hours),
        "level_1_fits": level_1_fits,
        "level_2_fits": level_2_fits,
        "charging_label": charging_label,
        "charging_detail": charging_detail,
        "epa_range": epa_range,
        "usable_range": (
            usable_range.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if usable_range is not None
            else None
        ),
        "range_headroom": (
            range_headroom.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if range_headroom is not None
            else None
        ),
        "range_days": (
            range_days.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if range_days is not None
            else None
        ),
        "range_fits": range_fits,
        "range_label": range_label,
        "range_detail": range_detail,
        "reserve_percent": int(reserve_percent),
        "station_count": len(stations),
        "networks": networks,
        "network_count": len(networks),
        "closest_station": closest_station,
        "closest_distance": closest_distance,
        "coverage_label": coverage_label,
        "coverage_detail": coverage_detail,
    }
