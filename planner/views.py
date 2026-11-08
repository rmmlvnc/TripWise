from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Sum
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import RegisterForm, TripForm, ExpenseForm, PhotoForm
from . import services
from .models import Trip, Expense


class CustomerLoginView(LoginView):
    template_name = "planner/login.html"
    redirect_authenticated_user = True


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome to TripWise! Let's plan your first adventure.")
        return redirect("dashboard")
    return render(request, "planner/register.html", {"form": form})


@login_required
def dashboard(request):
    trips = Trip.objects.filter(owner=request.user).order_by("start_date")
    expenses = Expense.objects.filter(trip__owner=request.user)
    budget = trips.aggregate(total=Sum("budget"))["total"] or Decimal("0")
    spent = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    query = request.GET.get("q", "").strip()[:200]
    status = request.GET.get("status", "all")
    if status not in ("all", "upcoming", "ongoing", "past"):
        status = "all"
    visible = trips
    if query:
        visible = visible.filter(destination__icontains=query)
    if status == "upcoming":
        visible = visible.filter(start_date__gt=date.today())
    elif status == "ongoing":
        visible = visible.filter(start_date__lte=date.today(), end_date__gte=date.today())
    elif status == "past":
        visible = visible.filter(end_date__lt=date.today())
    page = Paginator(visible.order_by("start_date", "pk").prefetch_related("photos"), 9).get_page(request.GET.get("page"))
    return render(request, "planner/dashboard.html", {
        "trips": page, "page_obj": page, "query": query, "status": status,
        "filtered_count": page.paginator.count, "trip_count": trips.count(),
        "upcoming_count": trips.filter(start_date__gte=date.today()).count(),
        "total_budget": budget, "total_spent": spent, "remaining": budget - spent,
        "recent_expenses": expenses.select_related("trip").order_by("-date", "-pk")[:5],
    })


@login_required
def trip_form(request, pk=None):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user) if pk else None
    form = TripForm(request.POST or None, instance=trip)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if trip and "destination" in form.changed_data:
            saved.latitude = None
            saved.longitude = None
            saved.location_label = ""
        saved.owner = request.user
        saved.save()
        messages.success(request, "Your trip has been saved.")
        return redirect("trip_detail", pk=saved.pk)
    return render(request, "planner/trip_form.html", {"form": form, "trip": trip})


@login_required
def trip_detail(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user)
    form = ExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.trip = trip
        expense.save()
        messages.success(request, "Expense added.")
        return redirect("trip_detail", pk=pk)
    expenses = trip.expenses.order_by("-date", "-pk")
    spent = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    percent = min(int(spent / trip.budget * 100), 100) if trip.budget else (100 if spent else 0)
    return render(request, "planner/trip_detail.html", {
        "trip": trip, "form": form, "expenses": expenses,
        "spent": spent, "remaining": trip.budget - spent, "percent": percent,
        "photo_form": PhotoForm(), "currencies": services.CURRENCIES,
        "over_budget": max(spent - trip.budget, Decimal("0")),
    })


@login_required
def trip_delete(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user)
    if request.method == "POST":
        try:
            for photo in trip.photos.all():
                services.delete_cloud_photo(photo.public_id)
                photo.delete()
        except services.APIError as exc:
            messages.error(request, str(exc))
            return redirect("trip_detail", pk=pk)
        trip.delete()
        messages.success(request, "Trip and its expenses deleted.")
        return redirect("dashboard")
    return render(request, "planner/trip_delete.html", {"trip": trip})


@login_required
@require_POST
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, trip__owner=request.user)
    trip_id = expense.trip_id
    expense.delete()
    messages.success(request, "Expense removed.")
    return redirect("trip_detail", pk=trip_id)


@login_required
def help_page(request):
    return render(request, "planner/help.html")
