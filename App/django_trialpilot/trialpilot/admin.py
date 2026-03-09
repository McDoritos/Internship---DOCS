from django.contrib import admin
from .models import Document, Version, Patient_profile, Treatment

# Register your models here.
admin.site.register(Document)
admin.site.register(Version)
admin.site.register(Patient_profile)
admin.site.register(Treatment)
