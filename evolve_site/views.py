from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.http import JsonResponse
from .forms import FuelSavingsForm, RegisterForm, Level2ChargerForm, StationSearchForm
from .models import FuelEconomyVehicle, Level2CalculatorSubmission, StationStatus
from .services import NRELClient
from decimal import Decimal
from django.views.generic import TemplateView, CreateView
from django.views.generic.edit import FormView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_cookie
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views import View
from django.db import DatabaseError
from django.conf import settings


def get_vehicle_year_choices():
    """
    Return model years from the locally synchronized FuelEconomy.gov catalog.
    """
    try:
        years = (
            FuelEconomyVehicle.objects.filter(is_active=True)
            .values_list('model_year', flat=True)
            .distinct()
            .order_by('-model_year')
        )
        return [('', '--- Choose a Year ---')] + [(year, year) for year in years]
    except DatabaseError:
        return [('', '--- Vehicle data unavailable ---')]

def get_manufacturers(request):
    """
    Returns a JSON list of manufacturers for a given model year.
    """
    year = request.GET.get('year')
    manufacturers = []
    if year:
        try:
            manufacturers = list(
                FuelEconomyVehicle.objects.filter(model_year=year, is_active=True)
                .values_list('manufacturer', flat=True)
                .distinct()
                .order_by('manufacturer')
            )
        except DatabaseError:
            manufacturers = []
    return JsonResponse({'manufacturers': manufacturers})

def get_models(request):
    """
    Return exact EPA vehicle options for a given year and manufacturer.
    """
    year = request.GET.get('year')
    manufacturer = request.GET.get('manufacturer')
    models = []
    if year and manufacturer:
        try:
            models = get_vehicle_options(year, manufacturer)
        except DatabaseError:
            models = []
    return JsonResponse({'models': models})


def get_vehicle_options(year, manufacturer):
    vehicles = list(
        FuelEconomyVehicle.objects.filter(
            model_year=year,
            manufacturer=manufacturer,
            is_active=True,
        ).order_by("model", "drivetrain", "fueleconomy_id")
    )
    label_counts = {}
    for vehicle in vehicles:
        label_counts[vehicle.option_label] = label_counts.get(vehicle.option_label, 0) + 1

    return [
        {
            "id": vehicle.fueleconomy_id,
            "label": (
                f"{vehicle.option_label} · EPA #{vehicle.fueleconomy_id}"
                if label_counts[vehicle.option_label] > 1
                else vehicle.option_label
            ),
        }
        for vehicle in vehicles
    ]


def populate_vehicle_form_choices(form, year=None, manufacturer=None):
    """Populate and validate the shared dependent vehicle selectors."""
    form.fields["model_year"].choices = get_vehicle_year_choices()
    try:
        manufacturers = (
            FuelEconomyVehicle.objects.filter(model_year=year, is_active=True)
            .values_list("manufacturer", flat=True)
            .distinct()
            .order_by("manufacturer")
            if year
            else []
        )
        form.fields["manufacturer"].choices = [
            ("", "--- Choose a Make ---")
        ] + [(make, make) for make in manufacturers]

        options = get_vehicle_options(year, manufacturer) if year and manufacturer else []
        form.fields["vehicle_id"].choices = [
            ("", "--- Choose a Model ---")
        ] + [(str(option["id"]), option["label"]) for option in options]
    except DatabaseError:
        form.fields["manufacturer"].choices = [
            ("", "--- Vehicle data unavailable ---")
        ]
        form.fields["vehicle_id"].choices = [
            ("", "--- Vehicle data unavailable ---")
        ]


def fuel_savings_calculator(request):
    """
    Handles the fuel savings calculator form and displays results.
    """
    context = {}
    results = {}
    
    if request.method == 'POST':
        form = FuelSavingsForm(request.POST)
        populate_vehicle_form_choices(
            form,
            request.POST.get("model_year"),
            request.POST.get("manufacturer"),
        )

        if form.is_valid():
            # Extract cleaned data from the form
            mpg = form.cleaned_data['mpg']
            gas_price = form.cleaned_data['gas_price']
            annual_miles = form.cleaned_data['annual_miles']
            electricity_cost = form.cleaned_data['electricity_cost']
            
            # Resolve the exact EPA option rather than ambiguous model text.
            try:
                ev = FuelEconomyVehicle.objects.get(
                    fueleconomy_id=form.cleaned_data['vehicle_id'],
                    model_year=form.cleaned_data['model_year'],
                    manufacturer=form.cleaned_data['manufacturer'],
                    is_active=True,
                )

                # Perform calculations
                gallons_per_year = Decimal(annual_miles) / mpg
                annual_gas_cost = gallons_per_year * gas_price
                kwh_per_year = (
                    Decimal(annual_miles)
                    * ev.combined_kwh_per_100_miles
                    / Decimal('100')
                )
                annual_electricity_cost = kwh_per_year * electricity_cost
                annual_savings = annual_gas_cost - annual_electricity_cost

                results = {
                    'annual_gas_cost': round(annual_gas_cost, 2),
                    'annual_electricity_cost': round(annual_electricity_cost, 2),
                    'annual_savings': round(annual_savings, 2),
                    'monthly_savings': round(annual_savings / 12, 2),
                    'five_year_savings': round(annual_savings * 5, 2),
                    'selected_ev': ev,
                }
            except FuelEconomyVehicle.DoesNotExist:
                form.add_error(None, "The selected electric vehicle could not be found.")

    else:
        form = FuelSavingsForm()
        populate_vehicle_form_choices(form)

    context['form'] = form
    context['results'] = results
    return render(request, 'evolve_site/calculator.html', context)

class HomeView(TemplateView):
    """
    Serves the main home page.
    """
    template_name = 'evolve_site/home.html'

class RegisterView(CreateView):
    """
    Handles user registration using a class-based view.
    On successful registration, the user is redirected to the login page.
    """
    form_class = RegisterForm
    success_url = reverse_lazy('evolve_site:login')
    template_name = 'evolve_site/register.html'

class Level2ChargerCalculatorView(FormView):
    template_name = 'evolve_site/level2_calculator.html'
    form_class = Level2ChargerForm
    success_url = reverse_lazy('evolve_site:level2_calculator')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        year = self.request.POST.get('model_year') or self.request.GET.get('model_year')
        manufacturer = self.request.POST.get('manufacturer') or self.request.GET.get('manufacturer')
        populate_vehicle_form_choices(form, year, manufacturer)
        return form

    def form_valid(self, form):
        year = form.cleaned_data['model_year']
        manufacturer = form.cleaned_data['manufacturer']
        vehicle_id = form.cleaned_data['vehicle_id']
        daily_miles = form.cleaned_data['daily_miles']
        charging_hours = form.cleaned_data['charging_hours']

        ev = FuelEconomyVehicle.objects.filter(
            fueleconomy_id=vehicle_id,
            model_year=year,
            manufacturer=manufacturer,
            is_active=True,
        ).first()
        if not ev:
            form.add_error("vehicle_id", "Selected EV not found.")
            return self.form_invalid(form)

        daily_kwh_needed = (
            Decimal(daily_miles)
            * ev.combined_kwh_per_100_miles
            / Decimal("100")
        )

        charge_rate_120 = Decimal("1.4")  # kW for Level 1 (120V)
        charge_rate_240 = Decimal("7.2")  # kW for Level 2 (240V)

        charge_hours_120 = round(daily_kwh_needed / charge_rate_120, 2)
        charge_hours_240 = round(daily_kwh_needed / charge_rate_240, 2)

        if charge_hours_120 <= charging_hours:
            recommendation = "Standard outlet (120V) is sufficient for your needs."
        else:
            recommendation = "Level 2 charger (240V) recommended for your daily driving habits."

        return self.render_to_response(self.get_context_data(
            form=form,
            recommendation=recommendation,
            selected_ev=ev,
            charge_hours_120=charge_hours_120,
            charge_hours_240=charge_hours_240
        ))

@staff_member_required
def calculator_submissions_report(request):
    """
    Admin-only view: Displays a report of all Level 2 calculator submissions.
    """
    submissions = Level2CalculatorSubmission.objects.all().order_by('-submitted_at')
    return render(request, 'evolve_site/calculator_submissions_report.html', {
        'submissions': submissions
    })

def cache_station_view(view_class):
    """Cache production station searches while keeping local feedback live."""
    if settings.DEBUG:
        return view_class
    decorated = method_decorator(vary_on_cookie, name='dispatch')(view_class)
    return method_decorator(cache_page(60 * 15), name='dispatch')(decorated)


@cache_station_view
class StationListView(TemplateView):
    """
    Displays a list of charging stations with pagination.
    Caching applied per ADR-0005.
    """
    template_name = 'evolve_site/station_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = StationSearchForm(self.request.GET or None)
        stations = []
        source_station_count = 0
        filters_active = False
        error_message = None

        if form.is_valid():
            search_type = form.cleaned_data['search_type']
            
            # Get location based on search type
            if search_type == 'zip':
                location = form.cleaned_data['zip_code']
            else:  # city
                location = form.cleaned_data['city_state']
            
            stations = NRELClient.get_stations(location)
            source_station_count = len(stations)
            
            if not stations and location:
                error_message = "No stations found or API unavailable. Please try again."

            connector_type = form.cleaned_data.get('connector_type')
            network = form.cleaned_data.get('network')
            filters_active = bool(connector_type or network)

            if connector_type:
                selected_connector = connector_type.upper()
                stations = [
                    station for station in stations
                    if selected_connector in {
                        str(connector).upper()
                        for connector in (station.get('ev_connector_types') or [])
                    }
                ]

            if network:
                selected_network = network.lower()
                stations = [
                    station for station in stations
                    if selected_network in str(station.get('ev_network') or '').lower()
                ]
            
            # Merge local status
            if stations:
                station_ids = [str(s['id']) for s in stations]
                # Get the most recent status for each station
                from django.db.models import Max
                latest_statuses = (
                    StationStatus.objects
                    .filter(nrel_station_id__in=station_ids)
                    .values('nrel_station_id')
                    .annotate(latest=Max('updated_at'))
                )
                latest_ids = {s['nrel_station_id']: s['latest'] for s in latest_statuses}
                
                # Get the actual status records
                status_records = StationStatus.objects.filter(
                    nrel_station_id__in=station_ids,
                    updated_at__in=latest_ids.values()
                )
                status_map = {s.nrel_station_id: s.status for s in status_records}

                for station in stations:
                    station_id = str(station['id'])
                    station['local_status'] = status_map.get(station_id)
        
        # Pagination (ADR-0005 FR-BASELINE-2)
        paginator = Paginator(stations, 10)  # 10 stations per page
        page_number = self.request.GET.get('page')
        
        try:
            page_obj = paginator.get_page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.get_page(1)
        except EmptyPage:
            page_obj = paginator.get_page(paginator.num_pages)
        
        context['form'] = form
        context['page_obj'] = page_obj
        context['paginator'] = paginator
        context['stations'] = stations
        context['source_station_count'] = source_station_count
        context['filters_active'] = filters_active
        context['error_message'] = error_message
        return context

class SubmitStationStatusView(LoginRequiredMixin, View):
    """AJAX view for submitting station status updates."""
    
    login_url = '/login/'  # Specify login URL for the mixin
    
    def post(self, request, *args, **kwargs):
        from .forms import StationStatusForm
        form = StationStatusForm(request.POST)
        if form.is_valid():
            StationStatus.objects.create(
                nrel_station_id=form.cleaned_data['station_id'],
                status=form.cleaned_data['status'],
                user=request.user
            )
            return JsonResponse({
                'success': True,
                'status': form.cleaned_data['status']
            })
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
    def handle_no_permission(self):
        """Return JSON error instead of redirecting for AJAX requests."""
        return JsonResponse({'success': False, 'error': 'Login required'}, status=403)
