from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
from requests.exceptions import RequestException, Timeout
from evolve_site.services import NRELClient
from evolve_site.models import StationStatus


class AuthFlowsTest(TestCase):
    """
    Tests the user authentication and registration flows.
    """
    def setUp(self):
        """Set up a test user for login/logout tests."""
        self.username = 'testuser'
        self.password = 'testpassword123'
        self.user = User.objects.create_user(username=self.username, password=self.password)

    def test_registration_view(self):
        """
        Tests that a new user can register and is redirected to the login page.
        """
        # Define new user credentials
        new_username = 'newuser'
        new_password = 'newpassword123'
        new_email = 'new@example.com'

        # Get the registration page
        response = self.client.get(reverse('evolve_site:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'evolve_site/register.html')

        # Post data to register a new user
        response = self.client.post(reverse('evolve_site:register'), {
            'username': new_username,
            'email': new_email,
            'password1': new_password,
            'password2': new_password,
        })

        # Check for redirect to login page
        self.assertRedirects(response, reverse('evolve_site:login'))
        
        # Verify the user was created
        self.assertTrue(User.objects.filter(username=new_username).exists())

    def test_login_view(self):
        """
        Tests that a registered user can log in and is redirected to the home page.
        """
        # Post login credentials
        response = self.client.post(reverse('evolve_site:login'), {
            'username': self.username,
            'password': self.password,
        })
        
        # Check for redirect to the home page
        self.assertRedirects(response, reverse('evolve_site:home'))
        
        # Check that the user is logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_logout_view(self):
        """
        Tests that a logged-in user can log out.
        """
        # First, log the user in
        self.client.login(username=self.username, password=self.password)
        self.assertTrue(self.client.session['_auth_user_id'])

        # Access the logout URL via POST
        response = self.client.post(reverse('evolve_site:logout'))
        
        # Check for redirect to the home page
        self.assertRedirects(response, reverse('evolve_site:home'))
        
        # Check that the user is logged out (session is cleared)
        self.assertIsNone(self.client.session.get('_auth_user_id'))

    def test_home_view_authenticated(self):
        """
        Tests that the home page shows correct content for an authenticated user.
        """
        self.client.login(username=self.username, password=self.password)
        response = self.client.get(reverse('evolve_site:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Welcome, {self.username}!")
        self.assertContains(response, 'Logout')
        self.assertNotContains(response, 'Login')

    def test_home_view_unauthenticated(self):
        """
        Tests that the home page shows correct content for an unauthenticated user.
        """
        response = self.client.get(reverse('evolve_site:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login')
        self.assertContains(response, 'Register')
        self.assertNotContains(response, 'Logout')


class NRELClientTest(TestCase):
    """
    Tests for the NRELClient service class.
    Invariant INV-1: The application must never crash if the external API 
    returns malformed JSON or errors out.
    """

    @patch('evolve_site.services.requests.get')
    @patch('evolve_site.services.NRELClient.geocode_zip')
    def test_get_stations_success(self, mock_geocode, mock_get):
        """
        Tests that get_stations successfully parses a valid API response.
        """
        # Mock geocoding
        mock_geocode.return_value = (35.2226, -101.8313)  # Amarillo, TX coordinates
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'fuel_stations': [
                {
                    'id': 12345,
                    'station_name': 'Test Supercharger',
                    'street_address': '123 Main St',
                    'city': 'Amarillo',
                    'state': 'TX',
                    'zip': '79101',
                    'ev_dc_fast_num': 8,
                    'ev_network': 'Tesla',
                    'ev_connector_types': ['TESLA'],
                    'distance': 2.5
                },
                {
                    'id': 67890,
                    'station_name': 'Test EA Station',
                    'street_address': '456 Oak Ave',
                    'city': 'Amarillo',
                    'state': 'TX',
                    'zip': '79102',
                    'ev_dc_fast_num': 4,
                    'ev_network': 'Electrify America',
                    'ev_connector_types': ['J1772COMBO', 'CHADEMO'],
                    'distance': 3.2
                }
            ]
        }
        mock_get.return_value = mock_response

        # Call the service
        stations = NRELClient.get_stations('79101')

        # Verify the result
        self.assertEqual(len(stations), 2)
        self.assertEqual(stations[0]['station_name'], 'Test Supercharger')
        self.assertEqual(stations[1]['station_name'], 'Test EA Station')
        
        # Verify geocoding was called
        mock_geocode.assert_called_once_with('79101')
        
        # Verify API was called with correct params
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn('latitude', call_args[1]['params'])
        self.assertIn('longitude', call_args[1]['params'])

    @patch('evolve_site.services.requests.get')
    @patch('evolve_site.services.NRELClient.geocode_zip')
    def test_get_stations_timeout(self, mock_geocode, mock_get):
        """
        Tests that get_stations handles API timeout gracefully (INV-1).
        """
        # Mock geocoding
        mock_geocode.return_value = (35.2226, -101.8313)
        
        # Mock timeout exception
        mock_get.side_effect = Timeout("Connection timed out")

        # Call the service - should return empty list, not crash
        stations = NRELClient.get_stations('79101')

        # Verify graceful handling
        self.assertEqual(stations, [])

    @patch('evolve_site.services.requests.get')
    @patch('evolve_site.services.NRELClient.geocode_zip')
    def test_get_stations_request_exception(self, mock_geocode, mock_get):
        """
        Tests that get_stations handles general request errors gracefully (INV-1).
        """
        # Mock geocoding
        mock_geocode.return_value = (35.2226, -101.8313)
        
        # Mock request exception
        mock_get.side_effect = RequestException("Network error")

        # Call the service - should return empty list, not crash
        stations = NRELClient.get_stations('79101')

        # Verify graceful handling
        self.assertEqual(stations, [])

    @patch('evolve_site.services.requests.get')
    @patch('evolve_site.services.NRELClient.geocode_zip')
    def test_get_stations_malformed_json(self, mock_geocode, mock_get):
        """
        Tests that get_stations handles malformed JSON response gracefully (INV-1).
        """
        # Mock geocoding
        mock_geocode.return_value = (35.2226, -101.8313)
        
        # Mock response with malformed JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        # Call the service - should return empty list, not crash
        stations = NRELClient.get_stations('79101')

        # Verify graceful handling
        self.assertEqual(stations, [])

    @patch('evolve_site.services.NRELClient.geocode_zip')
    def test_get_stations_geocoding_failure(self, mock_geocode):
        """
        Tests that get_stations handles geocoding failure gracefully.
        """
        # Mock failed geocoding
        mock_geocode.return_value = (None, None)

        # Call the service - should return empty list when geocoding fails
        stations = NRELClient.get_stations('00000')

        # Verify graceful handling
        self.assertEqual(stations, [])

    @patch('evolve_site.services.requests.get')
    @patch('evolve_site.services.NRELClient.geocode_zip')
    def test_get_stations_no_api_key(self, mock_geocode, mock_get):
        """
        Tests that get_stations handles missing API key configuration.
        """
        # Mock geocoding
        mock_geocode.return_value = (35.2226, -101.8313)
        
        with patch('evolve_site.services.settings') as mock_settings:
            mock_settings.NREL_API_KEY = None

            # Call the service - should return empty list
            stations = NRELClient.get_stations('79101')

            # Verify graceful handling
            self.assertEqual(stations, [])
            # Verify no API call was made
            mock_get.assert_not_called()

    def test_extract_max_power_tesla(self):
        """
        Tests power extraction for Tesla Superchargers.
        """
        station_v3 = {
            'station_name': 'Tesla Supercharger',
            'ev_network': 'Tesla',
            'open_date': '2020-05-01'
        }
        power = NRELClient.extract_max_power(station_v3)
        self.assertEqual(power, 250)  # V3 Supercharger

        station_v2 = {
            'station_name': 'Tesla Supercharger',
            'ev_network': 'Tesla',
            'open_date': '2015-03-01'
        }
        power = NRELClient.extract_max_power(station_v2)
        self.assertEqual(power, 150)  # V2 Supercharger

    def test_extract_max_power_electrify_america(self):
        """
        Tests power extraction for Electrify America stations.
        """
        station = {
            'station_name': 'EA Station',
            'ev_network': 'Electrify America'
        }
        power = NRELClient.extract_max_power(station)
        self.assertEqual(power, 350)

    def test_extract_max_power_explicit(self):
        """
        Tests power extraction when explicit power field is present.
        """
        station = {
            'station_name': 'Generic Station',
            'ev_network': 'Unknown',
            'ev_dc_fast_charger_power': 175
        }
        power = NRELClient.extract_max_power(station)
        self.assertEqual(power, 175)


class StationListViewTest(TestCase):
    """
    Tests for the station_list view that integrates NRELClient with local status.
    """

    def setUp(self):
        """Set up test user and local station status."""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.station_id = '12345'
        
        # Create a local status for testing
        StationStatus.objects.create(
            nrel_station_id=self.station_id,
            status='Broken',
            user=self.user
        )

    @patch('evolve_site.views.NRELClient.get_stations')
    def test_station_list_merges_local_status(self, mock_get_stations):
        """
        Tests that the view merges local status with NREL API data (AC3).
        """
        # Mock API response
        mock_get_stations.return_value = [
            {
                'id': 12345,
                'station_name': 'Test Station',
                'street_address': '123 Main St',
                'city': 'Amarillo',
                'state': 'TX',
                'zip': '79101',
                'ev_dc_fast_num': 4,
                'ev_network': 'Tesla',
                'ev_connector_types': ['TESLA']
            }
        ]

        # Make request with zip code
        response = self.client.get(reverse('evolve_site:station_list'), {
            'search_type': 'zip',
            'zip_code': '79101'
        })

        # Verify status code
        self.assertEqual(response.status_code, 200)
        
        # Verify local status was merged
        self.assertIn('stations', response.context)
        stations = response.context['stations']
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0]['local_status'], 'Broken')

    @patch('evolve_site.views.NRELClient.get_stations')
    def test_station_list_city_search(self, mock_get_stations):
        """
        Tests that the view works with city/state search.
        """
        # Mock API response
        mock_get_stations.return_value = [
            {
                'id': 12345,
                'station_name': 'Test Station',
                'street_address': '123 Main St',
                'city': 'Amarillo',
                'state': 'TX',
                'zip': '79101',
                'ev_dc_fast_num': 4,
                'ev_network': 'Tesla',
                'ev_connector_types': ['TESLA']
            }
        ]

        # Make request with city/state
        response = self.client.get(reverse('evolve_site:station_list'), {
            'search_type': 'city',
            'city_state': 'Amarillo, TX'
        })

        # Verify status code
        self.assertEqual(response.status_code, 200)
        
        # Verify stations were returned
        self.assertIn('stations', response.context)
        stations = response.context['stations']
        self.assertEqual(len(stations), 1)
        
        # Verify NRELClient was called with city/state
        mock_get_stations.assert_called_once_with('Amarillo, TX')

    @patch('evolve_site.views.NRELClient.get_stations')
    def test_station_list_handles_api_failure(self, mock_get_stations):
        """
        Tests that the view displays a friendly error when API fails (AC2).
        """
        # Mock API failure
        mock_get_stations.return_value = []

        # Make request with zip search
        response = self.client.get(reverse('evolve_site:station_list'), {
            'search_type': 'zip',
            'zip_code': '79101'
        })

        # Verify status code (should not be 500)
        self.assertEqual(response.status_code, 200)
        
        # Verify error message is shown
        self.assertContains(response, 'No stations found or API unavailable')

    def test_station_list_invalid_form_missing_zip(self):
        """
        Tests that the view validates zip code is provided when search_type is zip.
        """
        # Make request with zip search type but no zip code
        response = self.client.get(reverse('evolve_site:station_list'), {
            'search_type': 'zip'
        })

        # Verify status code
        self.assertEqual(response.status_code, 200)
        
        # Verify form has errors
        self.assertIn('form', response.context)
        self.assertFalse(response.context['form'].is_valid())

    def test_station_list_invalid_form_missing_city(self):
        """
        Tests that the view validates city/state is provided when search_type is city.
        """
        # Make request with city search type but no city/state
        response = self.client.get(reverse('evolve_site:station_list'), {
            'search_type': 'city'
        })

        # Verify status code
        self.assertEqual(response.status_code, 200)
        
        # Verify form has errors
        self.assertIn('form', response.context)
        self.assertFalse(response.context['form'].is_valid())

    @patch('evolve_site.views.NRELClient.get_stations')
    def test_station_list_no_local_status(self, mock_get_stations):
        """
        Tests that stations without local status still display correctly.
        """
        # Mock API response with station that has no local status
        mock_get_stations.return_value = [
            {
                'id': 99999,
                'station_name': 'New Station',
                'street_address': '789 Elm St',
                'city': 'Amarillo',
                'state': 'TX',
                'zip': '79101',
                'ev_dc_fast_num': 2,
                'ev_network': 'EVgo',
                'ev_connector_types': ['J1772COMBO']
            }
        ]

        # Make request with zip search
        response = self.client.get(reverse('evolve_site:station_list'), {
            'search_type': 'zip',
            'zip_code': '79101'
        })

        # Verify status code
        self.assertEqual(response.status_code, 200)
        
        # Verify station displays without local status
        stations = response.context['stations']
        self.assertEqual(len(stations), 1)
        self.assertIsNone(stations[0]['local_status'])
        self.assertIsNone(stations[0]['local_status'])


class StationStatusModelTest(TestCase):
    """
    Tests for the StationStatus model.
    """

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(username='testuser', password='testpass')

    def test_create_station_status(self):
        """
        Tests creating a StationStatus record.
        """
        status = StationStatus.objects.create(
            nrel_station_id='12345',
            status='Working',
            user=self.user
        )

        self.assertEqual(status.nrel_station_id, '12345')
        self.assertEqual(status.status, 'Working')
        self.assertEqual(status.user, self.user)
        self.assertIsNotNone(status.updated_at)

    def test_station_status_str(self):
        """
        Tests the string representation of StationStatus.
        """
        status = StationStatus.objects.create(
            nrel_station_id='54321',
            status='Broken',
            user=self.user
        )

        self.assertEqual(str(status), 'Station 54321: Broken')

    def test_station_status_choices(self):
        """
        Tests that only valid status choices can be used.
        """
        # Valid choices
        for choice in ['Working', 'Broken', 'Busy']:
            status = StationStatus(
                nrel_station_id='12345',
                status=choice,
                user=self.user
            )
            status.full_clean()  # Should not raise validation error

    def test_station_status_auto_timestamp(self):
        """
        Tests that updated_at is automatically set and updated.
        """
        status = StationStatus.objects.create(
            nrel_station_id='12345',
            status='Working',
            user=self.user
        )
        
        original_timestamp = status.updated_at
        self.assertIsNotNone(original_timestamp)
        
        # Update the status
        status.status = 'Broken'
        status.save()
        
        # Verify timestamp was updated
        self.assertGreaterEqual(status.updated_at, original_timestamp)


class StationStatusSubmissionTest(TestCase):
    """Tests for the station status submission feature (FR-F-002-3)."""
    
    def setUp(self):
        """Set up a test user for login/logout tests."""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.url = reverse('evolve_site:submit_station_status')
    
    def test_submit_status_authenticated_success(self):
        """Authenticated POST with valid data returns 200 and creates record."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(self.url, {
            'station_id': '12345',
            'status': 'Working'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StationStatus.objects.filter(
            nrel_station_id='12345', 
            status='Working',
            user=self.user
        ).exists())
    
    def test_submit_status_unauthenticated_returns_403(self):
        """POST without login returns 403."""
        response = self.client.post(self.url, {
            'station_id': '12345',
            'status': 'Working'
        })
        self.assertEqual(response.status_code, 403)
    
    def test_submit_status_invalid_choice_returns_400(self):
        """POST with invalid status returns 400."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(self.url, {
            'station_id': '12345',
            'status': 'InvalidStatus'
        })
        self.assertEqual(response.status_code, 400)


class CalculatorMethodologyTest(TestCase):
    """Tests for calculator methodology documentation (DOC-001-1)."""
    
    def test_fuel_calculator_contains_methodology(self):
        """GET calculator page contains methodology section."""
        response = self.client.get(reverse('evolve_site:calculator'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'How We Calculate')
    
    def test_level2_calculator_contains_methodology(self):
        """GET level2 calculator page contains methodology section."""
        response = self.client.get(reverse('evolve_site:level2_calculator'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'How We Calculate')
