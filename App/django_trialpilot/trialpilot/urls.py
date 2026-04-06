from django.urls import path
from django.shortcuts import render
from .views import diary_list, parameter_extraction, document_upload, patient_list, index, diary_remove, diary_details, patient_reset, trial_list, trial_details, trial_remove, criteria_conversion
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('documents/upload/', document_upload, name='document_upload'),
    path('documents/upload/success/', lambda request: render(request, 'trialpilot/document_upload_success.html'), name='document_upload_success'),
    
    path('patients/', patient_list, name='patient_list'),
    path('patients/<int:patient_id>/reset', patient_reset, name='patient_reset'),
    
    path('diaries/', diary_list, name='diary_list'),
    path('diaries/<int:diary_id>/extract/', parameter_extraction, name='parameter_extraction'),
    path('diaries/delete/', diary_remove, name='diary_remove'),
    path('diaries/<int:diary_id>/', diary_details, name="diary_details"),
    
    path('trials/', trial_list, name='trial_list'),
    path('diaries/<int:diary_id>/convert/', criteria_conversion, name='criteria_conversion'),
    path('trials/delete/', trial_remove, name='trial_remove'),
    path('trials/<int:trial_id>/', trial_details, name="trial_details"),
    
    path('', index, name='index'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
