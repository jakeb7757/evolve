from django import forms
from .models import ElectricVehicle, Level2CalculatorSubmission
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class FuelSavingsForm(forms.Form):
    """
    Form for calculating fuel savings between a gas car and an EV.
    """
    mpg = forms.DecimalField(
        label="Vehicle MPG",
        min_value=0.1,
        help_text="Your current gas vehicle's miles per gallon."
    )
    gas_price = forms.DecimalField(
        label="Gas Price ($/gallon)",
        min_value=0.01,
        help_text="Current price of gasoline per gallon."
    )
    annual_miles = forms.IntegerField(
        label="Annual Miles Driven",
        min_value=1,
        help_text="Total miles you drive in a year."
    )
    electricity_cost = forms.DecimalField(
        label="Electricity Cost ($/kWh)",
        min_value=0.01,
        help_text="Your home electricity rate per kilowatt-hour."
    )
    # The single EV dropdown is replaced by three dependent fields.
    # The choices for these will be set dynamically in the view.
    model_year = forms.ChoiceField(
        label="Year",
        choices=[], # Populated by the view
    )
    manufacturer = forms.ChoiceField(
        label="Make",
        choices=[], # Populated by JavaScript
    )
    model = forms.ChoiceField(
        label="Model",
        choices=[], # Populated by JavaScript
    )

class RegisterForm(UserCreationForm):
    """
    A form for registering a new user, inheriting from Django's UserCreationForm.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

class Level2ChargerForm(forms.Form):
    model_year = forms.ChoiceField(label="Year", choices=[])
    manufacturer = forms.ChoiceField(label="Make", choices=[])
    model = forms.ChoiceField(label="Model", choices=[])
    daily_miles = forms.IntegerField(label="Average Daily Miles", min_value=0)
    charging_hours = forms.IntegerField(label="Available Charging Hours per Night", min_value=1, max_value=24)
    home_voltage = forms.ChoiceField(label="Home Outlet Voltage", choices=[('110', '110V'), ('240', '240V')])

class StationSearchForm(forms.Form):
    SEARCH_TYPE_CHOICES = [
        ('zip', 'Zip Code'),
        ('city', 'City/State'),
    ]
    
    CONNECTOR_CHOICES = [
        ('', 'All Connectors'),
        ('CHADEMO', 'CHAdeMO'),
        ('J1772COMBO', 'CCS'),
        ('TESLA', 'Tesla/NACS'),
    ]
    
    NETWORK_CHOICES = [
        ('', 'All Networks'),
        ('Tesla', 'Tesla Supercharger'),
        ('Electrify America', 'Electrify America'),
        ('EVgo Network', 'EVgo'),
        ('ChargePoint Network', 'ChargePoint'),
        ('Blink Network', 'Blink'),
        ('Francis Energy', 'Francis Energy'),
    ]
    
    search_type = forms.ChoiceField(
        label="Search By",
        choices=SEARCH_TYPE_CHOICES,
        initial='zip',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    
    zip_code = forms.CharField(
        label="Zip Code", 
        max_length=10, 
        min_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter Zip Code (e.g., 79101)'
        })
    )
    
    city_state = forms.CharField(
        label="City, State",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Select or type a city...'
        })
    )
    
    connector_type = forms.ChoiceField(
        label="Connector Type",
        choices=CONNECTOR_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    network = forms.ChoiceField(
        label="Network",
        choices=NETWORK_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        search_type = cleaned_data.get('search_type')
        zip_code = cleaned_data.get('zip_code')
        city_state = cleaned_data.get('city_state')
        
        if search_type == 'zip' and not zip_code:
            self.add_error('zip_code', 'Zip code is required when searching by zip.')
        elif search_type == 'city' and not city_state:
            self.add_error('city_state', 'City and state are required when searching by city.')
        
        return cleaned_data

class StationStatusForm(forms.Form):
    """Form for submitting charging station status updates."""
    STATUS_CHOICES = [
        ('Working', 'Working'),
        ('Broken', 'Broken'),
        ('Busy', 'Busy'),
    ]
    
    station_id = forms.CharField(widget=forms.HiddenInput())
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Current Status"
    )