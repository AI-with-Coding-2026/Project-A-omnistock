from django import forms
from django.core.exceptions import ValidationError
from .models import OrderItem

class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        if product and quantity:
            if quantity <= 0:
                raise ValidationError({'quantity': "Quantity must be greater than zero."})
            
            if quantity > product.quantity_in_stock:
                raise ValidationError({
                    'quantity': f"Insufficient stock. Only {product.quantity_in_stock} unit(s) available for {product.name}."
                })

        return cleaned_data