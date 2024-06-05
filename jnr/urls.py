from django.contrib import admin
from django.urls import path
from backend.views import  process

urlpatterns = [
    path('admin/', admin.site.urls),
    path('process/', process, name='process'),
]
