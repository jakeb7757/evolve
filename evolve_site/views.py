from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.http import JsonResponse
from .forms import FuelSavingsForm, RegisterForm, Level2ChargerForm, StationSearchForm
from .models import ElectricVehicle, Level2CalculatorSubmission, StationStatus
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

def get_manufacturers(request):
    """
    Returns a JSON list of manufacturers for a given model year.
    """
    year = request.GET.get('year')
    manufacturers = []
    if year:
        manufacturers = list(
            ElectricVehicle.objects.filter(model_year=year)
            .values_list('manufacturer', flat=True)
            .distinct()
            .order_by('manufacturer')
        )
    return JsonResponse({'manufacturers': manufacturers})

def get_models(request):
    """
    Returns a JSON list of models for a given year and manufacturer.
    """
    year = request.GET.get('year')
    manufacturer = request.GET.get('manufacturer')
    models = []
    if year and manufacturer:
        models = list(
            ElectricVehicle.objects.filter(model_year=year, manufacturer=manufacturer)
            .values_list('model', flat=True)
            .distinct()
            .order_by('model')
        )
    return JsonResponse({'models': models})

def fuel_savings_calculator(request):
    """
    Handles the fuel savings calculator form and displays results.
    """
    context = {}
    results = {}
    
    # Get distinct years for the initial form dropdown
    year_choices = [('', '--- Choose a Year ---')] + [
        (year, year) for year in ElectricVehicle.objects.values_list('model_year', flat=True).distinct().order_by('-model_year')
    ]

    if request.method == 'POST':
        form = FuelSavingsForm(request.POST)
        # Set choices dynamically for validation
        form.fields['model_year'].choices = year_choices
        # We need to provide choices for manufacturer and model for the form to be valid,
        # even though they are selected via JS.
        if 'manufacturer' in request.POST:
            form.fields['manufacturer'].choices = [(request.POST['manufacturer'], request.POST['manufacturer'])]
        if 'model' in request.POST:
            form.fields['model'].choices = [(request.POST['model'], request.POST['model'])]

        if form.is_valid():
            # Extract cleaned data from the form
            mpg = form.cleaned_data['mpg']
            gas_price = form.cleaned_data['gas_price']
            annual_miles = form.cleaned_data['annual_miles']
            electricity_cost = form.cleaned_data['electricity_cost']
            
            # Find the selected EV based on the three form fields
            try:
                ev = ElectricVehicle.objects.get(
                    model_year=form.cleaned_data['model_year'],
                    manufacturer=form.cleaned_data['manufacturer'],
                    model=form.cleaned_data['model']
                )

                # Perform calculations
                gallons_per_year = Decimal(annual_miles) / mpg
                annual_gas_cost = gallons_per_year * gas_price
                efficiency_decimal = Decimal(str(ev.efficiency_wh_per_mile))
                kwh_per_year = (Decimal(annual_miles) * efficiency_decimal) / Decimal('1000')
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
            except ElectricVehicle.DoesNotExist:
                form.add_error(None, "The selected electric vehicle could not be found.")

    else:
        form = FuelSavingsForm()
        form.fields['model_year'].choices = year_choices

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
        year_choices = [('', '--- Choose a Year ---')] + [
            (year, year) for year in ElectricVehicle.objects.values_list('model_year', flat=True).distinct().order_by('-model_year')
        ]
        form.fields['model_year'].choices = year_choices

        year = self.request.POST.get('model_year') or self.request.GET.get('model_year')
        if year:
            manufacturers = ElectricVehicle.objects.filter(model_year=year).values_list('manufacturer', flat=True).distinct().order_by('manufacturer')
            form.fields['manufacturer'].choices = [('', '--- Choose a Make ---')] + [(m, m) for m in manufacturers]
        else:
            form.fields['manufacturer'].choices = [('', '--- Choose a Make ---')]

        manufacturer = self.request.POST.get('manufacturer') or self.request.GET.get('manufacturer')
        if year and manufacturer:
            models = ElectricVehicle.objects.filter(model_year=year, manufacturer=manufacturer).values_list('model', flat=True).distinct().order_by('model')
            form.fields['model'].choices = [('', '--- Choose a Model ---')] + [(m, m) for m in models]
        else:
            form.fields['model'].choices = [('', '--- Choose a Model ---')]
        return form

    def form_valid(self, form):
        year = form.cleaned_data['model_year']
        manufacturer = form.cleaned_data['manufacturer']
        model = form.cleaned_data['model']
        daily_miles = form.cleaned_data['daily_miles']
        charging_hours = form.cleaned_data['charging_hours']
        home_voltage = form.cleaned_data['home_voltage']

        # Fetch the first matching EV from database
        ev = (
            ElectricVehicle.objects
            .filter(model_year=year, manufacturer=manufacturer, model=model)
            .order_by('id')
            .first()
        )
        if not ev:
            return self.render_to_response(self.get_context_data(form=form, recommendation="Selected EV not found."))

        battery_capacity = float(ev.battery_capacity_kwh)
        epa_range = float(ev.epa_range_miles)

        daily_kwh_needed = (daily_miles / epa_range) * battery_capacity

        charge_rate_110 = 1.4  # kW for Level 1 (110V)
        charge_rate_240 = 7.2  # kW for Level 2 (240V)

        charge_hours_110 = round(daily_kwh_needed / charge_rate_110, 2)
        charge_hours_240 = round(daily_kwh_needed / charge_rate_240, 2)

        if charge_hours_110 <= charging_hours:
            recommendation = "Standard outlet (110V) is sufficient for your needs."
        else:
            recommendation = "Level 2 charger (240V) recommended for your daily driving habits."

        return self.render_to_response(self.get_context_data(
            form=form,
            recommendation=recommendation,
            selected_ev=ev,
            charge_hours_110=charge_hours_110,
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

@method_decorator(cache_page(60 * 15), name='dispatch')
@method_decorator(vary_on_cookie, name='dispatch')
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
        error_message = None

        if form.is_valid():
            search_type = form.cleaned_data['search_type']
            
            # Get location based on search type
            if search_type == 'zip':
                location = form.cleaned_data['zip_code']
            else:  # city
                location = form.cleaned_data['city_state']
            
            stations = NRELClient.get_stations(location)
            
            if not stations and location:
                error_message = "No stations found or API unavailable. Please try again."
            
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
