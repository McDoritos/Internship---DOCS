from django import forms

class UploadDocumentForm(forms.Form):
    file = forms.FileField()
    type = forms.BooleanField(required=False)
