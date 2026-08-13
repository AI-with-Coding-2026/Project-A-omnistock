from django import forms

from .models import Product, Supplier

BASE_INPUT = (
    "w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm "
    "text-gray-900 placeholder-gray-400 bg-white "
    "focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent "
    "transition"
)

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'email', 'phone', 'address']


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['supplier', 'name', 'unit_price', 'stock_quantity', 'reorder_level']


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " " + BASE_INPUT).strip()
