from django import forms
from django.contrib.auth.forms import AuthenticationForm

BASE_INPUT = (
    "w-full rounded-lg border border-gray-300 px-4 py-3 text-sm "
    "text-gray-900 placeholder-gray-400 bg-white "
    "focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent "
    "transition"
)

class StyledLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": BASE_INPUT,
            "placeholder": "Enter your username",
            "autofocus": True,
        })
        self.fields["password"].widget.attrs.update({
            "class": BASE_INPUT + " pr-12",   # room for the eye icon
            "placeholder": "Enter your password",
            "id": "id_password",
        })