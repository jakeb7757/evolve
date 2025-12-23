# Evolve: Electric Vehicle Savings & Station Finder

Evolve is a Django-based web application designed to help users transition to electric vehicles (EVs). It features tools to calculate fuel savings, determine Level 2 home charging needs, and find charging stations using the NREL API.

## 🚀 Features

*   **Fuel Savings Calculator**: Compare the annual cost of a gas vehicle vs. an EV based on mileage, MPG, and local energy rates.
*   **Level 2 Charger Calculator**: Determine if a home Level 2 charger is necessary based on daily driving habits.
*   **Station Finder**: Locate EV charging stations and submit status reports (Working, Broken, Busy).
*   **User Accounts**: Register, login, and save calculator submissions.
*   **Admin Dashboard**: Manage vehicle data and view submission reports.

---

## Rubric Compliance

This project demonstrates all required Django concepts from the course rubric:

### ✅ Baseline Features (All Implemented)
- Complete request/response lifecycle
- URL routing with path converters
- Function-based and class-based views
- Template rendering and context
- Form handling with validation
- Model definitions and migrations
- Django Admin configuration
- User authentication (login/logout)
- Middleware configuration
- Static file handling
- Test suite with Django TestCase
- Environment variable configuration
- Session management
- Security (CSRF, XSS protection)

### ✅ Good Features (14 implemented, 4 required)
1. **Named URLs & URL Reversing** - All URLs use `app_name` namespace and named patterns; templates use `{% url %}`
2. **Class-Based Views** - `HomeView`, `RegisterView`, `Level2ChargerCalculatorView`, `StationListView`, `SubmitStationStatusView`
3. **Generic CBVs** - `TemplateView`, `CreateView`, `FormView`, `View` with proper mixins
4. **Template Inheritance** - All templates extend `base.html` with `{% extends %}` and `{% block %}`
5. **CSRF Protection** - All forms include `{% csrf_token %}`
6. **FormView with Success Redirect** - `Level2ChargerCalculatorView` implements proper form handling
7. **QuerySet Operations** - Filtering, ordering, distinct operations throughout
8. **Model Relationships** - ForeignKey relationships in `StationStatus` and `Level2CalculatorSubmission`
9. **ModelAdmin Customization** - `list_display`, `search_fields`, `list_filter` on all admin classes
10. **User Model Access** - Using `get_user_model()` for proper user references
11. **Built-in Middleware** - Security, CSRF, Authentication, Session, Messages
12. **Static File Collection** - `collectstatic` configuration for deployment
13. **Test Client & URL Reversing** - Tests use `reverse()` and `self.client`
14. **Split Settings** - Separate `base.py`, `local.py`, `production.py` configuration

### ✅ Better Features (4 implemented, 2 required)
1. **ModelForms** - `StationStatusForm` with proper validation and widgets
2. **Aggregation/Annotations** - Using `Max('updated_at')` to get latest station statuses
3. **View Decorators** - `@staff_member_required`, `@method_decorator(cache_page)`, `@method_decorator(vary_on_cookie)`
4. **Mock External Services** - Comprehensive test mocking of NREL API calls

### ✅ Best Features (2 implemented, 1 required)
1. **Caching Strategy** - Per-view caching with `@cache_page(60 * 15)` on `StationListView`
2. **Cache Optimization** - Using `vary_on_cookie` for user-specific cache behavior
3. **Observability** - Error handling, custom 404/500 pages, comprehensive logging ready

---

## 🛠️ Installation & Setup

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd project_evolve
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Mac/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables**:
    Create a `.env` file in the `project_evolve` root (next to `manage.py`) with the following:
    ```ini
    SECRET_KEY=your-secret-key-here
    DEBUG=True
    NREL_API_KEY=your-nrel-api-key  # Optional for station finder
    ```

5.  **Run migrations**:
    ```bash
    python manage.py migrate
    ```

6.  **Create a superuser** (for Admin access):
    ```bash
    python manage.py createsuperuser
    ```

7.  **Run the server**:
    ```bash
    python manage.py runserver
    ```

## 🧪 Running Tests

To run the test suite, including the mocked API tests:

```bash
python manage.py test evolve_site
```
## Project Structure

project_evolve/
├── evolve/                 # Project configuration
│   ├── settings/           # Split settings (base, local, production)
│   ├── urls.py             # Main URL routing
│   └── ...
├── evolve_site/            # Main application
│   ├── models.py           # Database models (ElectricVehicle, etc.)
│   ├── views.py            # View logic (Calculators, Reports)
│   ├── forms.py            # Forms for inputs
│   ├── services.py         # NREL API client
│   ├── tests.py            # Unit tests
│   └── templates/          project_evolve/
├── evolve/                 # Project configuration
│   ├── settings/           # Split settings (base, local, production)
│   ├── urls.py             # Main URL routing
│   └── ...
├── evolve_site/            # Main application
│   ├── models.py           # Database models (ElectricVehicle, etc.)
│   ├── views.py            # View logic (Calculators, Reports)
│   ├── forms.py            # Forms for inputs
│   ├── services.py         # NREL API client
│   ├── tests.py            # Unit tests
│   └── templates/

