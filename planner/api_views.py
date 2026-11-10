from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from .forms import PhotoForm
from .models import Trip, TripPhoto
from . import services


@login_required
@require_GET
def trip_api(request, pk, provider):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user)
    try:
        if provider == "destinations":
            results = services.search_destinations(request.GET.get("q", trip.destination))
            results = [{**item, "token": signing.dumps({**item, "trip": trip.pk, "user": request.user.pk}, salt="trip-location")} for item in results]
            return JsonResponse({"results": results})
        if provider == "weather":
            if trip.latitude is None or trip.longitude is None:
                raise services.APIError("Find and select your destination first to see its forecast.")
            return JsonResponse(services.weather(trip.latitude, trip.longitude, trip.start_date, trip.end_date))
        if provider == "currency":
            return JsonResponse(services.convert_budget(trip.budget, request.GET.get("currency", "USD")))
        if provider == "wikipedia":
            return JsonResponse(services.destination_info(trip.destination))
        return JsonResponse({"error": "Unknown service."}, status=404)
    except services.WeatherRateLimit as exc:
        response = JsonResponse({"error": str(exc), "retry_after": exc.retry_after}, status=429)
        response["Retry-After"] = str(exc.retry_after)
        return response
    except services.APIError as exc:
        return JsonResponse({"error": str(exc)}, status=503)


@login_required
@require_POST
def select_destination(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user)
    try:
        data = signing.loads(request.POST.get("token", ""), salt="trip-location", max_age=3600)
        if data["trip"] != trip.pk or data["user"] != request.user.pk:
            raise signing.BadSignature()
        trip.latitude, trip.longitude = data["lat"], data["lon"]
        trip.location_label = data["label"]
        trip.save(update_fields=["latitude", "longitude", "location_label"])
        messages.success(request, "Destination coordinates saved. Your forecast is ready to check.")
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        messages.error(request, "That destination selection expired. Please search again.")
    return redirect("trip_detail", pk=pk)


@login_required
@require_POST
def photo_upload(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.user)
    form = PhotoForm(request.POST, request.FILES)
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if form.is_valid():
        try:
            result = services.upload_photo(form.cleaned_data["photo"], trip.pk)
            TripPhoto.objects.create(trip=trip, url=result["url"], public_id=result["public_id"], caption=form.cleaned_data["caption"])
            messages.success(request, "Your photo has been saved.")
            if wants_json:
                return JsonResponse({"ok": True})
        except services.APIError as exc:
            text = getattr(exc, "admin_message", str(exc)) if request.user.is_staff else str(exc)
            if wants_json:
                return JsonResponse({"error": text}, status=502)
            messages.error(request, text)
    else:
        errors = [f"{form.fields[field].label}: {error}" for field, values in form.errors.items() for error in values]
        if wants_json:
            return JsonResponse({"error": " ".join(errors)}, status=400)
        for error in errors:
            messages.error(request, error)
    from django.urls import reverse
    return redirect(reverse("trip_detail", args=[pk]) + "#trip-photos")


@login_required
@require_POST
def photo_delete(request, pk):
    photo = get_object_or_404(TripPhoto, pk=pk, trip__owner=request.user)
    trip_id = photo.trip_id
    try:
        services.delete_cloud_photo(photo.public_id)
        photo.delete()
        messages.success(request, "Photo removed from your trip and Cloudinary.")
    except services.APIError as exc:
        messages.error(request, str(exc))
    return redirect("trip_detail", pk=trip_id)
