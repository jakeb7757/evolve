import requests
from django.conf import settings
import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

class NRELClient:
    BASE_URL = "https://developer.nlr.gov/api/alt-fuel-stations/v1/nearest.json"
    MIN_FAST_CHARGE_POWER_KW = 80

    @staticmethod
    def geocode_zip(zip_code):
        """Convert zip code to latitude/longitude using geopy."""
        try:
            geolocator = Nominatim(user_agent="evolve_ev_app")
            location = geolocator.geocode(f"{zip_code}, USA", timeout=5)
            if location:
                logger.info(f"Geocoded {zip_code} to ({location.latitude}, {location.longitude})")
                return location.latitude, location.longitude
            else:
                logger.warning(f"Could not geocode zip code: {zip_code}")
                return None, None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.error(f"Geocoding error: {str(e)}")
            return None, None

    @staticmethod
    def extract_max_power(station):
        """Return the highest documented connector power for a station."""
        powers = []

        # Retain compatibility with responses or fixtures using the older
        # station-level power field.
        explicit_power = station.get('ev_dc_fast_charger_power')
        if explicit_power is not None:
            try:
                powers.append(float(explicit_power))
            except (TypeError, ValueError):
                pass

        # Current NLR responses report power per connector within each charging
        # unit. Use those measured values instead of estimating by network.
        for charging_unit in station.get('ev_charging_units') or []:
            if not isinstance(charging_unit, dict):
                continue

            connectors = charging_unit.get('connectors') or {}
            if not isinstance(connectors, dict):
                continue

            for connector in connectors.values():
                if not isinstance(connector, dict):
                    continue
                try:
                    powers.append(float(connector.get('power_kw')))
                except (TypeError, ValueError):
                    continue

        valid_powers = [power for power in powers if power > 0]
        return max(valid_powers, default=None)

    @staticmethod
    def get_stations(location):
        """
        Get charging stations near a location.
        
        Args:
            location: Either a zip code (e.g., '79101') or city/state (e.g., 'Amarillo, TX')
        
        Returns:
            List of station dictionaries or empty list on error
        """
        api_key = getattr(settings, 'NREL_API_KEY', None)
        if not api_key:
            logger.error("NREL_API_KEY not configured in settings")
            return []

        # Geocode the location (works for both zip codes and city/state)
        latitude, longitude = NRELClient.geocode_zip(location)
        if latitude is None or longitude is None:
            logger.error(f"Failed to geocode location: {location}")
            return []

        params = {
            'latitude': latitude,
            'longitude': longitude,
            'fuel_type': 'ELEC',
            'ev_connector_type': 'CHADEMO,J1772COMBO,TESLA',  # DC Fast Charger types
            'ev_charging_level': 'dc_fast',
            'ev_power_kw_min': NRELClient.MIN_FAST_CHARGE_POWER_KW,
            'limit': 50,
            'status': 'E',
            'access': 'public',
            'radius': 25  # Search within 25 miles
        }

        try:
            logger.info(f"Requesting NREL API for DC Fast Chargers at coordinates: ({latitude}, {longitude})")
            response = requests.get(
                NRELClient.BASE_URL,
                params=params,
                headers={'X-Api-Key': api_key},
                timeout=10,
            )
            logger.info(f"NREL API response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            stations = data.get('fuel_stations', [])
            
            # Enforce the minimum again using the returned connector data so
            # pagination and the page's filters only see qualifying stations.
            filtered_stations = []
            for station in stations:
                max_power = NRELClient.extract_max_power(station)
                if (
                    (station.get('ev_dc_fast_num') or 0) <= 0
                    or max_power is None
                    or max_power < NRELClient.MIN_FAST_CHARGE_POWER_KW
                ):
                    continue

                station['max_power_kw'] = max_power

                logger.debug(
                    "Station: %s, Network: %s, Power: %s kW",
                    station.get('station_name'),
                    station.get('ev_network'),
                    station['max_power_kw'],
                )

                filtered_stations.append(station)
            
            logger.info(
                "Retrieved %s charging stations rated at least %s kW",
                len(filtered_stations),
                NRELClient.MIN_FAST_CHARGE_POWER_KW,
            )
            return filtered_stations
            
        except (requests.RequestException, ValueError) as error:
            response = getattr(error, 'response', None)
            status_code = getattr(response, 'status_code', None)
            error_detail = f"HTTP {status_code}" if status_code else type(error).__name__
            logger.error("NLR API request failed: %s", error_detail)
            return []
