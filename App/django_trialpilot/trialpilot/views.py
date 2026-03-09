import datetime
from django.shortcuts import render
from .models import Document, Version, Patient_profile, Treatment
from .forms import UploadDocumentForm

# Create your views here.
def diary_list(request):
    diaries = Document.objects.filter(type=False)
    return render(request, 'trialpilot/diary_list.html', {'diaries': diaries})

# Finish this function to save into the Documents model and create a new Version instance for the uploaded document, and verify if works
def upload_document(request):
    if request.method == 'POST':
        form = UploadDocumentForm(request.POST, request.FILES)
        
        if form.is_valid():
            file = form.cleaned_data['file']

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            new_filename = f"{file.name}_{timestamp}"

            with open(f"documents/{new_filename}", 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)
        
            return render(request, "upload_document.html", {'form': form})
                

def parameter_extraction(request):
    if request.method == 'POST':
        document_id = request.POST.get('document_id')
        
        print(f"Received document ID: {document_id}")
        
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            print(f"Document with ID {document_id} not found.")
            return render(request, 'parameter_extraction.html', {'error': 'Document not found.'})