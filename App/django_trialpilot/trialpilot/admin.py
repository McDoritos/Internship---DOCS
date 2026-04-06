from django.contrib import admin
from .models import Document, Version, Patient_profile, Treatment, Trial_criteria, Patient_trial_match, Criterion_evaluation

# Register your models here.
admin.site.register(Document)
admin.site.register(Version)
admin.site.register(Patient_profile)
admin.site.register(Treatment)
admin.site.register(Trial_criteria)
admin.site.register(Patient_trial_match)
admin.site.register(Criterion_evaluation)
