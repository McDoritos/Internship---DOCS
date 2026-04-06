import ast
import datetime
import uuid
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
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import uuid
from django.db import transaction
from django.db.models import Q
from pypdf import PdfReader
from pdf2image import convert_from_bytes
import pytesseract


GROQ_KEY = os.getenv("GROQ_API_KEY")

# Prompt Files
PARAMETER_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "parameter-extraction_prompt.txt"
SYS_PARAMETER_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "sys_parameter-extraction_prompt.txt"

CRITERIA_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "criteria-extraction_prompt.txt"
SYS_CRITERIA_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "sys_criteria-extraction_prompt.txt"

CRITERIA_CONVERSION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-conversion" / "criteria-conversion_prompt.txt"
SYS_CRITERIA_CONVERSION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-conversion" / "sys_criteria-conversion_prompt.txt"

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

import json

def load_prompt_files(system_prompt_path, user_prompt_path):
    with open(system_prompt_path, "r", encoding="utf-8") as sys_file, \
         open(user_prompt_path, "r", encoding="utf-8") as user_file:
        return sys_file.read(), user_file.read()


def build_prompt(template, replacements):
    """
    replacements: dict -> {"{{PLACEHOLDER}}": "value"}
    """
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def call_llm(system_prompt, user_prompt):
    completion = CLIENT.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        temperature=TEMP
    )
    return completion.choices[0].message.content


def run_json_prompt_pipeline(
    *,
    system_prompt_path,
    user_prompt_path,
    replacements,
    log_label=None,
    max_retries=3
):

    if log_label:
        print(f"Processing: {log_label}")

    system_prompt, user_prompt_template = load_prompt_files(
        system_prompt_path,
        user_prompt_path
    )

    user_prompt = build_prompt(user_prompt_template, replacements)

    for attempt in range(1, max_retries + 1):
        result = call_llm(system_prompt, user_prompt)

        try:
            return json.loads(result)
        except ValueError as e:
            print(f"[Attempt {attempt}/{max_retries}] Error parsing JSON: {e}")
            print("Raw model output:", result)

    raise ValueError(f"Failed to get valid JSON after {max_retries} attempts.")

def parameter_extraction_pipeline(document, document_content):
    return run_json_prompt_pipeline(
        system_prompt_path=SYS_PARAMETER_EXTRACTION_PROMPT_FILE,
        user_prompt_path=PARAMETER_EXTRACTION_PROMPT_FILE,
        replacements={
            "{{DIARY_TEXT}}": document_content
        },
        log_label=document.title
    )
    
def criteria_extraction_step(document, document_content):
    return run_json_prompt_pipeline(
        system_prompt_path=SYS_CRITERIA_EXTRACTION_PROMPT_FILE,
        user_prompt_path=CRITERIA_EXTRACTION_PROMPT_FILE,
        replacements={
            "{{TRIAL_TEXT}}": document_content
        },
        log_label=document.title
    )

def criteria_conversion_step(criteria_extracted):
    return run_json_prompt_pipeline(
        system_prompt_path=SYS_CRITERIA_CONVERSION_PROMPT_FILE,
        user_prompt_path=CRITERIA_CONVERSION_PROMPT_FILE,
        replacements={
            "{{CRITERIA_TEXT}}": json.dumps(criteria_extracted, ensure_ascii=False)
        },
        log_label="criteria conversion"
    )


def extract_document_text(document):
    file_path = f"documents/{document.title}"
    ext = os.path.splitext(document.title)[1].lower()

    with default_storage.open(file_path, "rb") as f:
        if ext == ".txt":
            return f.read().decode("utf-8", errors="ignore")

        elif ext == ".pdf":
            reader = PdfReader(f)
            text = ""

            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    
            if len(text.strip()) < 20:
                print("Extracted text is too short, trying OCR...")
                f.seek(0)
                data = f.read()
                images = convert_from_bytes(data)
                text = ""

                for img in images:
                    text += pytesseract.image_to_string(img) + "\n"

            return text.strip()

        else:
            raise ValueError(f"Unsupported file type: {ext}")

def document_save(document, file, new_filename, version_id):
    saved_path = default_storage.save(
        f"documents/{new_filename}",
        file
    )
    
    Version.objects.create(
        document=document,
        version_name=f"{version_id}_{new_filename}",
        file_path=saved_path
    )
    
    print("Saving to:", default_storage.path(f"documents/{new_filename}"))

# Create your views here.
def trial_list(request):
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()
    file_type = request.GET.get("file_type", "").strip().lower()
    
    trials = Document.objects.filter(type=Document.DocumentType.CLINICAL_TRIAL)
    
    if search:
        trials = trials.filter(title__icontains=search)
        
    if status == "extracted":
        trials = trials.filter(extracted=True)
    elif status == "not_extracted":
        trials = trials.filter(extracted=False)
    
    trial_data = []
    for trial in trials:
        if "." in trial.title:
            original_name, ext = trial.title.rsplit('.', 1)
            ext = ext.lower()
        else:
            ext = ""

        # Filter by file type
        if file_type and ext != file_type:
            continue

        trial_data.append((trial, ext))

    return render(request, 'trialpilot/trial_list.html', {
        'trial_data': trial_data,
        'search': search,
        'status': status,
        'file_type': file_type,
    })
    
def diary_list(request):
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()
    file_type = request.GET.get("file_type", "").strip().lower()
    
    diaries = Document.objects.filter(type=Document.DocumentType.CLINICAL_DIARY)

    if search:
        diaries = diaries.filter(title__icontains=search)
        
    if status == "extracted":
        diaries = diaries.filter(extracted=True)
    elif status == "not_extracted":
        diaries = diaries.filter(extracted=False)

    
    diary_data = []
    for diary in diaries:
        if "." in diary.title:
            original_name, ext = diary.title.rsplit('.', 1)
            ext = ext.lower()
        else:
            ext = ""

        # Filter by file type
        if file_type and ext != file_type:
            continue

        diary_data.append((diary, ext))

    return render(request, 'trialpilot/diary_list.html', {
        'diary_data': diary_data,
        'search': search,
        'status': status,
        'file_type': file_type,
    })
    
def diary_details(request, diary_id):
    
    try:
        document = Document.objects.get(id=diary_id)
        
        if document.type != Document.DocumentType.CLINICAL_DIARY:
            return render(request, 'trialpilot/diary_details.html', {
                'error': 'Document is not a clinical diary.'
            })

            
        document_content = extract_document_text(document)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/diary_details.html', {
            'error': 'Document not found.'
        })

    versions = Version.objects.filter(document=document)

    patient = Patient_profile.objects.filter(document=document).first()

    treatments = Treatment.objects.filter(patient=patient) if patient else []

    return render(request, 'trialpilot/diary_details.html', {
        "diary": document,
        "diary_contents": document_content,
        "versions": versions,
        "patient": patient,
        "treatments": treatments
    })
    
def trial_details(request, trial_id):
    try:
        document = Document.objects.get(id=trial_id)
        if document.type != Document.DocumentType.CLINICAL_TRIAL:
            return render(request, 'trialpilot/trial_details.html', {
            'error': 'Document is not a clinical trial.'
        })
        document_content = extract_document_text(document)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/trial_details.html', {
            'error': 'Document not found.'
        })
   
    versions = Version.objects.filter(document=document)
    

@csrf_exempt
def diary_remove(request):
    if request.method == "POST":
        data = json.loads(request.body)
        diary_ids = data.get("diaries", [])

        for diary_id in diary_ids:
            document = get_object_or_404(Document, id=diary_id)

            versions = Version.objects.filter(document=document)
            for version in versions:
                version_path = os.path.join(
                    settings.MEDIA_ROOT,
                    version.file_path.name
                )

                print(f"Path of the version of the document {version_path}")
                
                if os.path.exists(version_path):
                    print("Version removed")
                    os.remove(version_path)

                version.delete()

            file_path = os.path.join(
                settings.MEDIA_ROOT,
                document.title
            )

            if os.path.exists(file_path):
                os.remove(file_path)

            document.delete()

        messages.success(request, 'Selected diaries have been deleted successfully.')
        
        return JsonResponse({"status": "success"})
    
@csrf_exempt
def trial_remove(request):
    if request.method == "POST":
        data = json.loads(request.body)
        trial_ids = data.get("trials", [])

        for trial_id in trial_ids:
            document = get_object_or_404(Document, id=trial_id)

            versions = Version.objects.filter(document=document)
            for version in versions:
                version_path = os.path.join(
                    settings.MEDIA_ROOT,
                    version.file_path.name
                )

                print(f"Path of the version of the document {version_path}")
                
                if os.path.exists(version_path):
                    print("Version removed")
                    os.remove(version_path)

                version.delete()

            file_path = os.path.join(
                settings.MEDIA_ROOT,
                document.title
            )

            if os.path.exists(file_path):
                os.remove(file_path)

            document.delete()

        messages.success(request, 'Selected trials have been deleted successfully.')
        
        return JsonResponse({"status": "success"})

    
def patient_list(request):
    search = request.GET.get("search", "").strip()
    stage = request.GET.get("stage", "").strip()
    molecular_status = request.GET.get("molecular_status", "").strip()
    
    patients = Patient_profile.objects.all()
    
    if search:
        patients = patients.filter(
            Q(diagnosis__icontains=search) |
            Q(molecular_status__icontains=search) |
            Q(stage__icontains=search) |
            Q(control__icontains=search)
        )
    
    if stage:
        patients = patients.filter(stage__icontains=stage)

    if molecular_status:
        patients = patients.filter(molecular_status__icontains=molecular_status)
    
    patient_data = []
    for patient in patients:
        treatments = Treatment.objects.filter(patient=patient)
        patient_data.append((patient, treatments))

    return render(request, 'trialpilot/patient_list.html', {
        'patient_data': patient_data,
        'search': search,
        'stage': stage,
        'molecular_status': molecular_status,
    })

@transaction.atomic
def patient_reset(request, patient_id):
    if request.method == 'POST':
        patient = Patient_profile.objects.get(id=patient_id)
        document = patient.document

        patient.delete()
        
        if not document.patient_profiles.exists():
            document.extracted = False

            versions = Version.objects.filter(document=document)

            for version in versions:
                if 'RAW' not in version.version_name:
                    path = os.path.join(settings.MEDIA_ROOT, version.file_path.name)

                    if os.path.exists(path):
                        os.remove(path)

                    version.delete()
                else:
                    continue

            document.save() 
        
        messages.success(request, f"All patient's information and diary data reseted successfully")
        
        return JsonResponse({"status": "ok"})
    

def document_upload(request):
    if request.method == 'POST':
        form = UploadDocumentForm(request.POST, request.FILES)

        if form.is_valid():
            files = request.FILES.getlist('file')

            doc_type = (
                Document.DocumentType.CLINICAL_TRIAL 
                if form.cleaned_data['type'] 
                else Document.DocumentType.CLINICAL_DIARY
            )

            for file in files:
                timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")

                original_name, ext = file.name.rsplit('.', 1)
                unique_id = uuid.uuid4().hex
                new_filename = f"{original_name}_{unique_id}.{ext}"
                
                

                document = Document.objects.create(
                    title=new_filename,
                    type=doc_type
                )

                document_save(document, file, new_filename, version_id='RAW')

            messages.success(request, f"{len(files)} clinical diaries uploaded successfully.")
            return redirect('diary_list')

    else:
        form = UploadDocumentForm()

    return render(request, "trialpilot/document_upload.html", {'form': form})

def parameter_extraction(request, diary_id):
    try:
        document = Document.objects.get(id=diary_id)
        document_content = extract_document_text(document)
        
        if not document_content.strip():
            return render(request, 'trialpilot/diary_parameter-extraction.html', {
                'error': 'Could not extract readable text from this document.'
            })
    except Document.DoesNotExist:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Document not found.'})
    
    if document.extracted:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Parameters have already been extracted and validated for this document.'})
    elif document.type != Document.DocumentType.CLINICAL_DIARY:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'This pipeline only accepts Clinical Diary documents.'})
    else:
        if request.method == 'GET':
            
            extracted_params = parameter_extraction_pipeline(document, document_content)
            
            #extracted_params = dummy_params
            
            file_params = ContentFile(json.dumps(extracted_params))

            original_name, ext = document.title.rsplit('.', 1)
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"
            
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
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"
            
            document_save(document, file_params, new_filename, 'VALIDATED')
            
            document.extracted = True
            document.save()

            messages.success(request, "Parameters extracted and validated with success. And a new patient profile has been created.")
            return redirect('diary_list')

def criteria_conversion(request, trial_id):
    try:
        document = Document.objects.get(id=trial_id)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/trial_criteria-conversion.html', {
            'error': 'Document not found.'
        })

    if document.type != Document.DocumentType.CLINICAL_TRIAL:
        return render(request, 'trialpilot/trial_criteria-conversion.html', {
            'error': 'This pipeline only accepts Clinical Trial documents.'
        })

    document_content = extract_document_text(document)

    if not document_content.strip():
        return render(request, 'trialpilot/trial_criteria-conversion.html', {
            'error': 'Could not extract readable text from this document.'
        })
    else:
        if request.method == 'GET':
            criteria_extracted = criteria_extraction_step(document, document_content)
            
            criteria_converted = criteria_conversion_step(criteria_extracted)
            
            parsed_criteria = ContentFile(json.dumps(criteria_converted))
            
            original_name, ext = document.title.rsplit('.', 1)
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"
            
            document_save(document, parsed_criteria, new_filename, 'CONVERTED')
            
            return render(request, 'trialpilot/trial_criteria-conversion.html', {"trial": document, "trial_content": document_content, "converted_criteria": criteria_converted})
        
        elif request.method == 'POST':
            corrected_criteria = request.POST.dict()
            corrected_criteria.pop("csrfmiddlewaretoken", None)
            
            json_string = json.dumps(corrected_criteria)
            
            


def index(request):
    n_diaries = Document.objects.filter(type=Document.DocumentType.CLINICAL_DIARY).count()
    n_trials = Document.objects.filter(type=Document.DocumentType.CLINICAL_TRIAL).count()
    n_patients = Patient_profile.objects.count()
    n_versions = Version.objects.count()

    total_docs = Document.objects.count()
    avg_versions = n_versions / total_docs if total_docs > 0 else 0

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