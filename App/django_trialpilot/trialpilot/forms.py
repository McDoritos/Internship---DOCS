from django import forms
from django.core.validators import FileExtensionValidator

ext_validator = FileExtensionValidator(allowed_extensions=["pdf", "txt"], message="Only PDF and TXT files are allowed.")

class UploadDocumentForm(forms.Form):
    file = forms.FileField(validators=[ext_validator])
    type = forms.BooleanField(required=False)

class UploadTrialForm(forms.Form):
    file = forms.FileField(validators=[ext_validator])
    type = forms.BooleanField(required=False)
    study_name = forms.CharField(max_length=255)
    pathology_group = forms.ChoiceField(choices=[
        ("cabeca_pescoco", "Cabeça e Pescoço"),
        ("dermatologia", "Dermatologia"),
        ("digestivo", "Digestivo"),
        ("ginecologia", "Ginecologia"),
        ("mama", "Mama"),
        ("oncologia_pediatrica", "Oncologia Pediátrica"),
        ("pele", "Pele"),
        ("pneumologia", "Pneumologia"),
        ("snc", "Tumores do Sistema Nervoso Central"),
        ("tne", "Tumores Neuroendócrinos")
    ])
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    status = forms.ChoiceField(choices=[
        ("recruiting", "Recruiting"),
        ("closed", "Closed"),
        ("not_yet", "Not Yet Recruiting"),
        ("completed", "Completed")
    ])
    