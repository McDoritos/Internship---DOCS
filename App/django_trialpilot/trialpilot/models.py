from django.db import models

# Create your models here.
class Document(models.Model):
    class DocumentType(models.TextChoices):
        CLINICAL_DIARY = "diary", "Clinical Diary"
        CLINICAL_TRIAL = "trial", "Clinical Trial"

    title = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=DocumentType.choices)
    extracted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
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
    class pathologyGroupType(models.TextChoices):
        CABECAPESCOCO = "cabeca_pescoco", "Cabeça e Pescoço"
        DERMATOLOGIA = "dermatologia", "Dermatologia"
        DIGESTIVO = "digestivo", "Digestivo"
        GINECOLOGIA = "ginecologia", "Ginecologia"
        MAMA = "mama", "Mama"
        ONCOLOGIA_PEDIATRICA = "oncologia_pediatrica", "Oncologia Pediátrica"
        PELE = "pele", "Pele"
        PNEUMOLOGIA = "pneumologia", "Pneumologia"
        SNC = "snc", "Tumores do Sistema Nervoso Central"
        TNE = "tne", "Tumores Neuroendócrinos"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="patient_profiles")
    age = models.IntegerField(null=True, blank=True)
    ecog_ps = models.IntegerField(null=True, blank=True)
    diagnosis = models.CharField(max_length=255, null=True, blank=True)
    diagnosis_date = models.DateField(null=True, blank=True)
    molecular_status = models.CharField(max_length=255, null=True, blank=True)
    stage = models.CharField(max_length=50, null=True, blank=True)
    control = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    pathology_group = models.CharField(max_length=255, null=True, blank=True, choices=pathologyGroupType.choices)
    
    
    def __str__(self):
        return f"Patient {self.id} - {self.diagnosis}"    

class Treatment(models.Model):
    patient = models.ForeignKey(Patient_profile, on_delete=models.CASCADE, related_name="treatments")
    treatment_name = models.CharField(max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.patient} - {self.treatment_name}"
    
class Analysis(models.Model):
    patient = models.ForeignKey(Patient_profile, on_delete=models.CASCADE, related_name="analysis")

    leucocitos = models.FloatField(null=True, blank=True)
    neutrofilos = models.FloatField(null=True, blank=True)
    neutrofilos_percent = models.FloatField(null=True, blank=True)
    linfocitos = models.FloatField(null=True, blank=True)
    linfocitos_percent = models.FloatField(null=True, blank=True)
    monocitos = models.FloatField(null=True, blank=True)
    monocitos_percent = models.FloatField(null=True, blank=True)
    eosinofilos = models.FloatField(null=True, blank=True)
    eosinofilos_percent = models.FloatField(null=True, blank=True)
    basofilos = models.FloatField(null=True, blank=True)
    basofilos_percent = models.FloatField(null=True, blank=True)

    eritrocitos = models.FloatField(null=True, blank=True)
    hemoglobina = models.FloatField(null=True, blank=True)
    hematocrito = models.FloatField(null=True, blank=True)
    vc_medio = models.FloatField(null=True, blank=True)
    hcm = models.FloatField(null=True, blank=True)
    chcm = models.FloatField(null=True, blank=True)
    rdw = models.FloatField(null=True, blank=True)

    plaquetas = models.FloatField(null=True, blank=True)
    vpm = models.FloatField(null=True, blank=True)
    plaquetocrito = models.FloatField(null=True, blank=True)
    pdw = models.FloatField(null=True, blank=True)

    glicose = models.FloatField(null=True, blank=True)
    azoto_ureico = models.FloatField(null=True, blank=True)
    creatinina = models.FloatField(null=True, blank=True)
    sodio = models.FloatField(null=True, blank=True)
    potassio = models.FloatField(null=True, blank=True)
    proteinas_totais = models.FloatField(null=True, blank=True)
    albumina = models.FloatField(null=True, blank=True)
    calcio = models.FloatField(null=True, blank=True)
    osmolalidade = models.FloatField(null=True, blank=True)
    ldh = models.FloatField(null=True, blank=True)
    ast = models.FloatField(null=True, blank=True)
    alt = models.FloatField(null=True, blank=True)
    fosfatase_alcalina = models.FloatField(null=True, blank=True)
    gama_gt = models.FloatField(null=True, blank=True)
    bilirrubina_total = models.FloatField(null=True, blank=True)
    creatina_cinase = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Analysis for patient {self.patient.id}"
    
class Trial_criteria(models.Model):
    class CriterionType(models.TextChoices):
        INCLUSION = "inclusion", "Inclusion"
        EXCLUSION = "exclusion", "Exclusion"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="trial_criteria")
    type = models.CharField(max_length=20, choices=CriterionType.choices)
    
    raw_criterion = models.TextField()
    validated_criterion = models.TextField(blank=True, null=True)
    
    validated = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.document.title} - {self.type} Criterion: {self.validated_criterion}"
    
class Logic_criteria(models.Model):
    criterion = models.OneToOneField(
        Trial_criteria,
        on_delete=models.CASCADE,
        related_name="logic"
    )

    raw_logic = models.JSONField(blank=True, null=True)
    validated_logic = models.JSONField(blank=True, null=True)

    validated = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Logic for Criterion {self.criterion.id} - Validated: {self.validated}"
    
    
class Patient_trial_match(models.Model):
    class Decision(models.TextChoices):
        ELIGIBLE = "eligible", "Eligible"
        INELIGIBLE = "ineligible", "Ineligible"
        INCONCLUSIVE = "inconclusive", "Inconclusive"

    patient = models.ForeignKey(Patient_profile, on_delete=models.CASCADE, related_name="trial_matches")
    trial = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="patient_matches")

    decision = models.CharField(max_length=20, choices=Decision.choices)
    deterministic_result = models.BooleanField(default=False)

    llm_justification = models.TextField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)

    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("patient", "trial")

    def __str__(self):
        return f"{self.patient} ↔ {self.trial} ({self.decision})"

class Criterion_evaluation(models.Model):
    match = models.ForeignKey(Patient_trial_match, on_delete=models.CASCADE, related_name="criterion_evaluations")
    criterion = models.ForeignKey(Trial_criteria, on_delete=models.CASCADE, related_name="evaluations")

    passed = models.BooleanField()
    patient_value = models.CharField(max_length=255, null=True, blank=True)
    evaluation_details = models.JSONField(null=True, blank=True)

    deterministic_justification = models.TextField(null=True, blank=True)

    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("match", "criterion")

    def __str__(self):
        return f"{self.match} - Criterion {self.criterion.id} ({'PASS' if self.passed else 'FAIL'})"
    