from django import forms
from .models import GeoData

class GeoDataForm(forms.ModelForm):
    class Meta:
        model = GeoData
        fields = ['name', 'file']
