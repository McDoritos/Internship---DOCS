from django.urls import path
from django.shortcuts import render
from .views import diary_list, parameter_extraction, document_upload, patient_list, index, diary_remove, diary_details, patient_reset
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('diaries/', diary_list, name='diary_list'),
    path('documents/upload/', document_upload, name='document_upload'),
    path('documents/upload/success/', lambda request: render(request, 'trialpilot/document_upload_success.html'), name='document_upload_success'),
    path('diaries/<int:diary_id>/extract/', parameter_extraction, name='parameter_extraction'),
    path('patients/', patient_list, name='patient_list'),
    path('patients/<int:patient_id>/reset', patient_reset, name='patient_reset'),
    path('diaries/delete/', diary_remove, name='diary_remove'),
    path('diaries/<int:diary_id>/', diary_details, name="diary_details"),
    path('', index, name='index'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
