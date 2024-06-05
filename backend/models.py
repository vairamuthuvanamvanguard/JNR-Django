

from django.db import models
from django.conf import settings

def upload_to_jnr_works(instance, filename):
    return f'jnr_works/{filename}'

class GeoData(models.Model):
    name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to=upload_to_jnr_works)
