import requests
from django.conf import settings
import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

class NRELClient:
    BASE_URL = "https://developer.nrel.gov/api/alt-fuel-stations/v1/nearest.json"

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
        """Extract maximum charging power from station data."""
        max_power = None
        
        # Check for explicit power fields that NREL might provide
        if 'ev_dc_fast_charger_power' in station and station['ev_dc_fast_charger_power']:
            max_power = station['ev_dc_fast_charger_power']
            logger.info(f"Found explicit power: {max_power} kW for {station.get('station_name')}")
            return max_power
        
        # Check network-specific patterns
        network = station.get('ev_network', '').upper()
        station_name = station.get('station_name', '').upper()
        
        # Tesla Superchargers - check date or name for version hints
        if 'TESLA' in network:
            # Try to determine V2 vs V3 based on date or name
            date_updated = station.get('updated_at', '')
            open_date = station.get('open_date', '')
            
            # V3 Superchargers started rolling out in 2019
            # If we have a date and it's 2020+, likely V3 (250kW), otherwise V2 (150kW)
            if open_date and open_date >= '2020-01-01':
                max_power = 250  # V3
            elif open_date and open_date >= '2012-01-01':
                max_power = 150  # V2
            else:
                # Conservative estimate if no date info
                max_power = 150  # Assume V2 to be safe
                
        # Electrify America (typically 150-350kW)
        elif 'ELECTRIFY AMERICA' in network:
            max_power = 350
        # EVgo (typically 50-350kW, newer stations are higher)
        elif 'EVGO' in network:
            max_power = 350
        # ChargePoint (varies widely, be conservative)
        elif 'CHARGEPOINT' in network:
            max_power = 62.5
        # Francis Energy (often 150kW+)
        elif 'FRANCIS' in network:
            max_power = 150
        # Blink (typically 50kW)
        elif 'BLINK' in network:
            max_power = 50
        # Generic DC Fast is typically 50kW minimum
        else:
            max_power = 50
            
        return max_power

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
            'api_key': api_key,
            'latitude': latitude,
            'longitude': longitude,
            'fuel_type': 'ELEC',
            'ev_connector_type': 'CHADEMO,J1772COMBO,TESLA',  # DC Fast Charger types
            'ev_charging_level': 'dc_fast',  # Only DC Fast Chargers
            'limit': 50,
            'status': 'E',
            'access': 'public',
            'radius': 25  # Search within 25 miles
        }

        try:
            logger.info(f"Requesting NREL API for DC Fast Chargers at coordinates: ({latitude}, {longitude})")
            response = requests.get(NRELClient.BASE_URL, params=params, timeout=5)
            logger.info(f"NREL API response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            stations = data.get('fuel_stations', [])
            
            # Additional client-side filtering and power extraction
            filtered_stations = []
            for station in stations:
                # Check ev_dc_fast_num to ensure it has DC fast chargers
                if station.get('ev_dc_fast_num', 0) > 0:
                    # Add max power to station data
                    station['max_power_kw'] = NRELClient.extract_max_power(station)
                    
                    # Log station details for debugging
                    logger.debug(f"Station: {station.get('station_name')}, "
                               f"Network: {station.get('ev_network')}, "
                               f"Power: {station['max_power_kw']} kW, "
                               f"Open date: {station.get('open_date')}")
                    
                    filtered_stations.append(station)
            
            logger.info(f"Retrieved {len(filtered_stations)} DC Fast Charging stations")
            return filtered_stations
            
        except (requests.RequestException, ValueError) as e:  # Add ValueError here
            logger.error(f"NREL API request failed: {str(e)}")
            return []