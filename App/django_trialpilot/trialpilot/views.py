import ast
import datetime
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from httpx import request
from .models import Document, Version, Patient_profile, Treatment
from .forms import UploadDocumentForm
from groq import Groq
import os
from django.conf import settings
from pathlib import Path
import json
from django.db.models import Avg, Count



GROQ_KEY = os.getenv("GROQ_API_KEY")
PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "parameter-extraction_prompt.txt"
SYS_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "sys_parameter-extraction_prompt.txt"
CLIENT = Groq(api_key=GROQ_KEY)
MODEL = "openai/gpt-oss-120b"
TEMP = 0.7

dummy_params = {
    "age_or_birthdate": 45,
    "ecog_ps": 0,
    "diagnosis": "Invasive ductal carcinoma of the breast",
    "diagnosis_date": "2020-01-01",
    "molecular_status": "ER 90%, PR 40%, HER2 0 (negative)",
    "stage": "pT2N2M0 (Stage IIIA)",
    "treatments": [
        {
            "name": "Adjuvant radiotherapy",
            "start_date": "2025-01-15",
            "end_date": "2025-01-15"
        },
        {
            "name": "Carboplatin + Paclitaxel",
            "start_date": "2025-02-01",
            "end_date": "2025-06-15"
        }
    ],
    "control": (
        "Post‑treatment PET‑CT (2025-06-20) showed no residual uptake in the operated breast, "
        "reduced axillary adenopathy, and no distant metastases. "
        "Comorbidity: hypertension treated with Ramipril 5 mg. "
        "Ongoing follow‑up includes breast MRI scheduled for 2026-01-10 "
        "and PET‑CT on 2026-04-10."
    )
}

# Auxiliary functions

def clean_value(value):
    return None if value in ["None", "", "null", None] else value

def parameter_extraction_pipeline(document, document_content):
    with open(SYS_PROMPT_FILE,"r", encoding="utf-8") as sys_parameter_extraction_prompt_file, \
         open(PROMPT_FILE, "r", encoding="utf-8") as perfect_gen_prompt_file:
             
        base_parameter_extraction_prompt = perfect_gen_prompt_file.read()
        base_sys_parameter_extraction_prompt = sys_parameter_extraction_prompt_file.read()
        
    print(f"processing file: {document.title}")
    
    sys_parameter_extraction_prompt = base_sys_parameter_extraction_prompt
        
    parameter_extraction_prompt = base_parameter_extraction_prompt.replace("{{DIARY_TEXT}}",document_content)
    
    completion = CLIENT.chat.completions.create(
            model=MODEL, # llama-3.3-70b-versatile, openai/gpt-oss-120b the prompt isn-t optimized for gpt-oss-120b
            messages=[
                {
                    "role": "system",
                    "content": sys_parameter_extraction_prompt
                },
                {
                    "role": "user",
                    "content": parameter_extraction_prompt
                }
            ],
            temperature=TEMP
        )
    result = completion.choices[0].message.content
    
    try:
        parsed = json.loads(result)
    except ValueError as e:
        print(f"Error parsing the result as JSON: {e}")
        
        # Retrying the process until there is a valid JSON output
        return parameter_extraction_pipeline(document, document_content)
    
    return parsed

def document_save(document, file, new_filename, version_id):
    Version.objects.create(
        document=document,
        version_name=f"{version_id}_{new_filename}"
    )
    
    saved_path = default_storage.save(
        f"documents/{new_filename}",
        file
    )
    
    print("Saving to:", default_storage.path(f"documents/{new_filename}"))

# Create your views here.
def diary_list(request):
    diaries = Document.objects.filter(type=False)

    diary_data = []
    for diary in diaries:
        original_name, ext = diary.title.rsplit('.', 1)
        diary_data.append((diary, ext.lower()))

    return render(request, 'trialpilot/diary_list.html', {
        'diary_data': diary_data
    })
    
def patient_list(request):
    patients = Patient_profile.objects.all()
    patient_data = []
    for patient in patients:
        treatments = Treatment.objects.filter(patient=patient)
        patient_data.append((patient, treatments))

    return render(request, 'trialpilot/patient_list.html', {
        'patient_data': patient_data
    })

def document_upload(request):
    if request.method == 'POST':
        form = UploadDocumentForm(request.POST, request.FILES)
        print("Form errors:", form.errors)

        if form.is_valid():
            file = form.cleaned_data['file']
            doc_type = form.cleaned_data['type']

            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

            original_name, ext = file.name.rsplit('.', 1)
            new_filename = f"{original_name}_{timestamp}.{ext}"

            document = Document.objects.create(
                title=new_filename,
                type=doc_type
            )
            
            document_save(document, file, new_filename, version_id='RAW')
            
            messages.success(request, "Clinical diary uploaded successfully.")
            return redirect('diary_list') 

    else:
        form = UploadDocumentForm()

    return render(request, "trialpilot/document_upload.html", {'form': form})

# MISSING: Save the result of the LLM creating a new file and a new version on the database
def parameter_extraction(request, diary_id):
    try:
        document = Document.objects.get(id=diary_id)
        document_content = default_storage.open(f"documents/{document.title}").read().decode("utf-8")
    except Document.DoesNotExist:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Document not found.'})
    
    if document.extracted:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Parameters have already been extracted and validated for this document.'})
    else:
        if request.method == 'GET':
            print(f"Received document ID: {diary_id}")
            
            #extracted_params = parameter_extraction_pipeline(document, document_content)
            
            extracted_params = dummy_params
            
            file_params = ContentFile(json.dumps(extracted_params))
            
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

            original_name, ext = document.title.rsplit('.', 1)
            new_filename = f"{original_name}_{timestamp}.{ext}"
            
            document_save(document, file_params, new_filename, 'EXTRACTED')
            
            return render(request, 'trialpilot/diary_parameter-extraction.html', {"diary": document, "diary_content": document_content, "extracted_params": extracted_params})

            
        elif request.method == 'POST':
            corrected_params = request.POST.dict()
            corrected_params.pop("csrfmiddlewaretoken", None)
            
            json_string = json.dumps(corrected_params)
            
            patient = Patient_profile.objects.create(
                document=document,
                age=clean_value(corrected_params.get("age_or_birthdate")),
                ecog_ps=clean_value(corrected_params.get("ecog_ps")),
                diagnosis=clean_value(corrected_params.get("diagnosis")),
                diagnosis_date=clean_value(corrected_params.get("diagnosis_date")),
                molecular_status=clean_value(corrected_params.get("molecular_status")),
                stage=clean_value(corrected_params.get("stage")),
                control=clean_value(corrected_params.get("control")),
            )
            
            treatments_raw = corrected_params.get("treatments")
            print("Raw treatments data:", treatments_raw)

           
            try:
                treatments = ast.literal_eval(treatments_raw)
            except:
                treatments = []

            print("Parsed treatments data:", treatments)

            for treatment in treatments:
                print(f"Processing treatment: {treatment}")

                Treatment.objects.create(
                    patient=patient,
                    treatment_name=treatment.get("name"),
                    start_date=clean_value(treatment.get("start_date")),
                    end_date=clean_value(treatment.get("end_date")),
                )



            file_params = ContentFile(json_string)

            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

            original_name, ext = document.title.rsplit('.', 1)
            new_filename = f"{original_name}_{timestamp}.{ext}"
            
            document_save(document, file_params, new_filename, 'VALIDATED')
            
            document.extracted = True
            document.save()

            messages.success(request, "Parameters extracted and validated with success. And a new patient profile has been created.")
            return redirect('diary_list')

def index(request):
    n_diaries = Document.objects.filter(type=False).count()
    n_patients = Patient_profile.objects.count()
    n_trials = Document.objects.filter(type=True).count()
    n_versions = Version.objects.count()
    avg_versions = Version.objects.count() / Document.objects.count() if Document.objects.count() > 0 else 0
    
    avg_age = Patient_profile.objects.aggregate(Avg('age'))['age__avg']

    
    top_diagnoses = (
        Patient_profile.objects.values('diagnosis')
        .annotate(count=Count('id'))
        .order_by('-count')[:3]
    )

    
    return render(request, 'trialpilot/index.html', {
        'n_diaries': n_diaries,
        'n_patients': n_patients,
        'n_trials': n_trials,
        'n_versions': n_versions,
        'avg_versions': avg_versions,
        'avg_age': avg_age,
        'top_diagnoses': top_diagnoses,
    })