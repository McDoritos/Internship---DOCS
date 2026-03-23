from django.db import models

# Create your models here.
class Document(models.Model):
    title = models.CharField(max_length = 255)
    type = models.BooleanField(default=False)
    extracted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    
    def __str__(self):
        return f"{self.title} - {self.type}"
    
class Version(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name = "versions")
    version_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    file_path = models.FileField(upload_to='documents/', default=None)
    
    def __str__(self):
        return f"{self.document.title} - {self.version_name}"
    
class Patient_profile(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="patient_profiles")
    age = models.IntegerField(null=True, blank=True)
    ecog_ps = models.IntegerField(null=True, blank=True)
    diagnosis = models.CharField(max_length=255, null=True, blank=True)
    diagnosis_date = models.DateField(null=True, blank=True)
    molecular_status = models.CharField(max_length=255, null=True, blank=True)
    stage = models.CharField(max_length=50, null=True, blank=True)
    control = models.CharField(max_length=255, null=True, blank=True)
    
    def __str__(self):
        return f"Patient {self.id} - {self.diagnosis}"    

class Treatment(models.Model):
    patient = models.ForeignKey(Patient_profile, on_delete=models.CASCADE, related_name="treatments")
    treatment_name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.patient} - {self.treatment_name}"