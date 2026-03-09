from django.urls import path
from .views import diary_list, parameter_extraction

urlpatterns = [
    path('diaries/', diary_list, name='diary_list')
]