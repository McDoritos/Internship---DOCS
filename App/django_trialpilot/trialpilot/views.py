import datetime
from django.shortcuts import render, redirect
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import Document, Version, Patient_profile, Treatment
from .forms import UploadDocumentForm
from groq import Groq
import os
from django.conf import settings
from pathlib import Path


GROQ_KEY = os.getenv("GROQ_API_KEY")
PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "parameter-extraction_prompt.txt"
SYS_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "sys_parameter-extraction_prompt.txt"
CLIENT = Groq(api_key=GROQ_KEY)
MODEL = "openai/gpt-oss-120b"
TEMP = 0.7

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

            saved_path = default_storage.save(
                f"documents/{new_filename}",
                file
            )

            document = Document.objects.create(
                title=new_filename,
                type=doc_type
            )

            Version.objects.create(
                document=document,
                version_name=f"RAW_{new_filename}"
            )
            
            print("Saving to:", default_storage.path(f"documents/{new_filename}"))
            ContentFile(file.read())
            print("Uploaded size:", file.size)  
            print("Read size:", len(file.read()))
            
            return redirect('document_upload_success') 

    else:
        form = UploadDocumentForm()

    return render(request, "trialpilot/document_upload.html", {'form': form})

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
    
    return result

# MISSING: Save the result of the LLM creating a new file and a new version on the database
def parameter_extraction(request, diary_id):
    if request.method == 'POST':
        
        print(f"Received document ID: {diary_id}")
        
        try:
            document = Document.objects.get(id=diary_id)
            document_path = default_storage.path(f"documents/{document.title}")
            print(f"Document path: {document_path}")
            
            #Reading document content
            document_content = default_storage.open(f"documents/{document.title}").read().decode("utf-8")

            print(f"Document content size: {len(document_content)} bytes")
            
            extracted_params =parameter_extraction_pipeline(document, document_content)
            
            return render(request, 'trialpilot/diary_parameter-extraction.html', {"diary": document_content, "extracted_params": extracted_params})
            
        except Document.DoesNotExist:
            print(f"Document with ID {diary_id} not found.")
            return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Document not found.'})