import datetime
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import Document, Version, Patient_profile, Treatment
from .forms import UploadDocumentForm
from groq import Groq
import os
from django.conf import settings
from pathlib import Path
import json


GROQ_KEY = os.getenv("GROQ_API_KEY")
PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "parameter-extraction_prompt.txt"
SYS_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "sys_parameter-extraction_prompt.txt"
CLIENT = Groq(api_key=GROQ_KEY)
MODEL = "openai/gpt-oss-120b"
TEMP = 0.7
# Auxiliary functions


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
    return render(request, 'trialpilot/diary_list.html', {'diaries': diaries})

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
            
            return redirect('document_upload_success') 

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
            
            extracted_params = parameter_extraction_pipeline(document, document_content)
            
            file_params = ContentFile(json.dumps(extracted_params))
            
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

            original_name, ext = document.title.rsplit('.', 1)
            new_filename = f"{original_name}_{timestamp}.{ext}"
            
            document_save(document, file_params, new_filename, 'EXTRACTED')
            
            return render(request, 'trialpilot/diary_parameter-extraction.html', {"diary": document_content, "extracted_params": extracted_params})

            
        elif request.method == 'POST':
            corrected_params = request.POST.dict()
            corrected_params.pop("csrfmiddlewaretoken", None)
            
            json_string = json.dumps(corrected_params)
            file_params = ContentFile(json_string)

            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

            original_name, ext = document.title.rsplit('.', 1)
            new_filename = f"{original_name}_{timestamp}.{ext}"
            
            document_save(document, file_params, new_filename, 'VALIDATED')
            
            document.extracted = True
            document.save()

            messages.success(request, "Parâmetros extraídos e validados com sucesso.")
            return redirect('diary_list')


        