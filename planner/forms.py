from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Trip, Expense


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True, label="First name")
    last_name = forms.CharField(max_length=150, required=True, label="Last name")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hints = {"first_name": "given-name", "last_name": "family-name", "email": "email", "username": "username", "password1": "new-password", "password2": "new-password"}
        for name, hint in hints.items():
            self.fields[name].widget.attrs["autocomplete"] = hint

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ("destination", "start_date", "end_date", "budget", "notes")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Places to visit, things to remember…"}),
            "budget": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }
        labels = {"budget": "Total trip budget (PHP)"}
        help_texts = {
            "destination": "Include a city and country, for example Tokyo, Japan.",
            "start_date": "The first day of your trip.",
            "end_date": "The last day of your trip. Same-day trips are welcome.",
            "budget": "How much you plan to spend on the entire trip, in Philippine pesos.",
            "notes": "Optional: places to visit, travel details, or reminders.",
        }

    def clean_budget(self):
        value = self.cleaned_data["budget"]
        if value < 0:
            raise forms.ValidationError("Budget must be zero or greater.")
        return value

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            self.add_error("end_date", "End date must be on or after the start date.")
        return data


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("title", "amount", "date")
        labels = {"title": "What did you spend on?", "amount": "Amount paid (PHP)"}
        help_texts = {"title": "For example: bus fare, lunch, or hotel.", "amount": "Enter this expense in Philippine pesos.", "date": "The day you paid for this expense."}
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }

    def clean_amount(self):
        value = self.cleaned_data["amount"]
        if value <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return value


class PhotoForm(forms.Form):
    photo = forms.ImageField(label="Photo", widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))
    caption = forms.CharField(max_length=200, required=False, label="Caption")

    def clean_photo(self):
        upload = self.cleaned_data["photo"]
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an image no larger than 5 MB.")
        if upload.image.format not in ("JPEG", "PNG", "WEBP"):
            raise forms.ValidationError("Only JPEG, PNG, and WebP images are supported.")
        return upload
