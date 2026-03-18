from django import forms
from django.core.validators import FileExtensionValidator

ext_validator = FileExtensionValidator(allowed_extensions=["pdf", "txt"], message="Only PDF and TXT files are allowed.")

class UploadDocumentForm(forms.Form):
    file = forms.FileField(validators=[ext_validator])
    type = forms.BooleanField(required=False)
