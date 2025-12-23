from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import HomeView, RegisterView, fuel_savings_calculator, Level2ChargerCalculatorView, get_manufacturers, get_models, calculator_submissions_report, SubmitStationStatusView

app_name = 'evolve_site'

urlpatterns = [
    # Home page
    path('', HomeView.as_view(), name='home'),

    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='evolve_site/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),

    # Calculator
    path('calculator/', fuel_savings_calculator, name='calculator'),
    path('level2-calculator/', Level2ChargerCalculatorView.as_view(), name='level2_calculator'),

    # API endpoints for dependent dropdowns
    path('api/manufacturers/', views.get_manufacturers, name='api_get_manufacturers'),
    path('api/models/', views.get_models, name='api_get_models'),

    path('get_manufacturers/', get_manufacturers, name='get_manufacturers'),
    path('get_models/', get_models, name='get_models'),

    # Admin reports
    path('admin/calculator-submissions/', calculator_submissions_report, name='calculator_submissions_report'),
    path('calculator-submissions-report/', calculator_submissions_report, name='calculator_submissions_report'),

    # Stations
    path('stations/', views.StationListView.as_view(), name='station_list'),
    path('stations/status/', SubmitStationStatusView.as_view(), name='submit_station_status'),
]