from django import forms
from .models import Customer, Order

BASE_INPUT = (
    "w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm "
    "text-gray-900 placeholder-gray-400 bg-white "
    "focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent "
    "transition"
)
class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['customer']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].required = False
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " " + BASE_INPUT).strip()

class BaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " " + BASE_INPUT).strip()

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'email', 'phone', 'address']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " " + BASE_INPUT).strip()