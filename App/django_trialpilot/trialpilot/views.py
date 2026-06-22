import ast
import datetime
import uuid
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from httpx import request
from .models import Criterion_evaluation, Document, Patient_trial_match, Version, Patient_profile, Treatment, Trial_criteria, Logic_criteria, Analysis, ClinicalTrial, Trial_cohort
from .forms import UploadDocumentForm, UploadTrialForm
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
import json
import re
from difflib import SequenceMatcher
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
import pandas as pd
from datetime import datetime
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta
import unicodedata
from time import sleep


GROQ_KEY = os.getenv("GROQ_API_KEY")

# Prompt Files
PARAMETER_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "parameter-extraction_prompt.txt"
SYS_PARAMETER_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "sys_parameter-extraction_prompt.txt"

CRITERIA_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "criteria-extraction_prompt.txt"
SYS_CRITERIA_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "sys_criteria-extraction_prompt.txt"

CRITERIA_EXTRACTION_COHORT_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "criteria-extraction-cohort_prompt.txt"
SYS_CRITERIA_EXTRACTION_COHORT_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "sys_criteria-extraction-cohort_prompt.txt"

SYS_TRIAL_STRUCTURE_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "trial-structure" / "sys_trial-structure_prompt.txt"
TRIAL_STRUCTURE_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "trial-structure" / "trial-structure_prompt.txt"

CRITERIA_CONVERSION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-conversion" / "criteria-conversion_prompt.txt"
SYS_CRITERIA_CONVERSION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-conversion" / "sys_criteria-conversion_prompt.txt"

MATCHING_PATIENTS_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "matching-patients" / "matching-patients_prompt.txt"
SYS_MATCHING_PATIENTS_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "matching-patients" / "sys_matching-patients_prompt.txt"

ANALYSIS_DIR = Path(settings.BASE_DIR) / "analysis"
ANALYSIS_FILES = list(ANALYSIS_DIR.glob("analysis_patient_*.txt"))

NORMALIZATION_DIR = Path(settings.BASE_DIR) / "normalization_sheet"
NORMALIZATION_FILES = list(NORMALIZATION_DIR.glob("normalization-sheet*.csv"))

PATIENT_TEXT_CACHE = {}

CLIENT = Groq(api_key=GROQ_KEY)
MODEL = "openai/gpt-oss-120b" # llama-3.3-70b-versatile, openai/gpt-oss-120b
TEMP = 0.7

DIAGNOSIS_OPTIONS = {
    "cabeca_pescoco": [
        "OM - CARCINOMA EPIDERMÓIDE  CAVIDADE ORAL",
        "OM - CARCINOMA EPIDERMÓIDE  CAVIDADE ORAL PALIATIVO",
        "OM - CARCINOMA EPIDERMÓIDE  CAVIDADE ORAL PALIATIVO PD-L1+",
        "OM - CARCINOMA  HIPOFARINGE",
        "OM - CARCINOMA  HIPOFARINGE PALIATIVO",
        "OM - CARCINOMA  HIPOFARINGE PALIATIVOPD-L1",
        "OM - CARCINOMA DE GLÂNDULAS SALIVARES",
        "OM - CARCINOMA DE GLÂNDULAS SALIVARES PALIATIVO",
        "OM - CARCINOMA DE GLÂNDULAS SALIVARES PALIATIVO PD-L1+",
        "OM - CARCINOMA FOSSAS NASAIS E SEIOS PERINANAIS",
        "OM - CARCINOMA FOSSAS NASAIS E SEIOS PERINANAIS PALIATIVO",
        "OM - CARCINOMA FOSSAS NASAIS E SEIOS PERINANAIS PALIATIVO PD-L1+",
        "OM - CARCINOMA LARINGE",
        "OM - CARCINOMA LARINGE PALIATIVO",
        "OM - CARCINOMA LARINGE PALIATIVO PD-L1+",
        "OM - CARCINOMA OROFARINGE",
        "OM - CARCINOMA OROFARINGE PALIATIVO",
        "OM - CARCINOMA OROFARINGE PALIATIVOPD-L1+",
        "OM - CARCINOMA EPIDERMÓIDE METASTASES CERVICAIS PRIMARIO OCULTO",
        "OM - CARCINOMA EPIDERMÓIDE METASTASES CERVICAIS PRIMARIO OCULTO PALIATIVO",
        "OM - CARCINOMA EPIDERMÓIDE METASTASES CERVICAIS PRIMARIO OCULTO PALIATIVO PD-L1+",
        "OM - CARCINOMA NASOFARINGE",
        "OM - CARCINOMA NASOFARINGE PALIATIVO",
        "OM - CARCINOMA NASOFARINGE PALIATIVO PD-L1+",
        "OM - CARCINOMA HIPOFARINGE",
        "OM - CARCINOMA HIPOFARINGE PALIATIVO",
        "OM - CARCINOMA HIPOFARINGE PALIATIVO PD-L1+",
        "OM - CARCINOMA NASOFARINGE",
        "OM - CARCINOMA NASOFARINGE PALIATIVO",
        "OM - CARCINOMA NASOFARINGE PALIATIVO PD-L1+",
    ],
    "dermatologia": [
        "OM - MELANOMA",
        "OM - MELANOMA PALIATIVO",
        "OM - MELANOMA PALIATIVO BRAF +",
        "OM - MELANOMA PALIATIVO NRAS +",
        "OM - MELANOMA PALIATIVO NF1 +",
        "OM - MELANOMA PALIATIVO KIT +",
        "OM - MELANOMA PALIATIVO PTEN +"
    ],
    "digestivo": [
        "OM - GASTRICO PERIOPERATORIO",
        "OM - GASTRICO ADJUVANTE",
        "OM - GASTRICO PALIATIVO",
        "OM - GASTRICO PALIATIVO HER2- CLAUDINA+",
        "OM - GASTRICO PALIATIVO MSI",
        "OM - GASTRICO PDL1+",
        "OM - VESICULA E VIAS BILIARES ADJUVANTE",
        "OM - VESICULA E VIAS BILIARES PALIATIVO",
        "OM - VESICULA E VIAS BILIARES PALIATIVO RAS MUTADO",
        "OM - VESICULA E VIAS BILIARES PALIATIVO HER2",
        "OM - VESICULA E VIAS BILIARES PALIATIVO BRAF",
        "OM - VESICULA E VIAS BILIARES PALIATIVO IDH MUTADO PALIATIVO",
        "OM - VESICULA E VIAS BILIARES PALIATIVO NTRK",
        "OM - VESICULA E VIAS BILIARES PALIATIVO FGFR2B",
        "OM - VESICULA BILIAR ADJUVANTE",
        "OM - AMPULOMA ADJUVANTE",
        "OM - AMPULOMA PALIATIVO",
        "OM - PANCREAS METASTIZADO",
        "OM - PANCREAS PALIAIVO BRCA+",
        "OM - PANCREAS PALIATIVO RAS+",
        "OM - PANCREAS PALIATIVO NTRK+",
        "OM - PANCREAS PALIATIVO MSI",
        "OM - ESOFAGO CARCINOMA EPIDERMOIDE PALIATIVO",
        "OM - ESOFAGO CARCINOMA EPIDERMOIDE DEFINITIVO",
        "OM - ESOFAGO CARCINOMA EPIDERMOIDE NEOADJUVANTE",
        "OM - ESOFAGO CARCINOMA EPIDERMOIDE PALIATIVO PD-L1+",
        "OM - ESOFAGO CARCINOMA EPIDERMOIDE PALIATIVO MSI",
        "OM - ESOFAGO ADENOCARCINOMA PERIOPERATORIO",
        "OM - ESOFAGO ADENOCARCINOMA NEOADJUVANTE",
        "OM - ESOFAGO ADENOCARCINOMA ADJUVANTE",
        "OM - ESOFAGO ADENOCARCINOMA PALIATIVO",
        "OM - ESOFAGO ADENOCARCINOMA PALIATIVO HER 2+",
        "OM - ESOFAGO ADENOCARCINOMA PALIATIVO MSI",
        "OM - ESOFAGO ADENOCARCINOMA PALIATIVO PD-L1+",
        "OM - CANAL ANAL LOCALMENTE AVANCADO",
        "OM - CANAL ANAL PALIATIVO",
        "OM - CANAL ANAL PALIATIVO MSI",
        "OM - HEPATOCARCINOMA BCLC B",
        "OM - HEPATOCARCINOMA BCLC C",
        "OM - ADENOCARCINOMA CÓLON LOCALMENTE AVANÇADO",
        "OM - ADENOCARCINOMA CÓLON LOCALMENTE AVANÇADO MSI-H",
        "OM - ADENOCARCINOMA CÓLON PALIATIVO",
        "OM - ADENOCARCINOMA COLORETAL PALIATIVO RAS WT",
        "OM - ADENOCARCINOMA COLORETAL PALIATIVO RAS MUTADO",
        "OM - ADENOCARCINOMA COLORETAL PALIATIVO BRAF MUTADO",
        "OM - ADENOCARCINOMA COLORETAL PALIATIVO MSI-H",
        "OM - ADENOCARCINOMA RETO LOCALMENTE AVANÇADO",
        "OM - ADENOCARCINOMA RETO LOCALMENTE AVANÇADO MSI-H"
    ],
    "ginecologia": [
        "OM - CARCINOMA ENDOMETRIO",
        "OM - CARCINOMA ENDOMETRIO PALIATIVO",
        "OM - CARCINOMA ENDOMETRIO MMRd",
        "OM - CARCINOMA COLO DO ÚTERO",
        "OM - CARCINOMA COLO DO ÚTERO PALIATIVO",
        "OM - CARCINOMA COLO DO ÚTERO PALIATIVO PD-L1 +",
        "OM - CARCIMOMA PRIMARIO PERITONEU",
        "OM - TUMORES MALIGNOS DE CÉLULAS GERMINATIVAS DO OVÁRIO",
        "OM - TUMOR DE CÉLULAS DA GRANULOSA",
        "OM - TUMOR DE CÉLULAS DE SERTOLI",
        "OM - TUMOR DOS CORDÕES SEXUAIS E ESTROMA",
        "OM - TUMOR SACO VITELINO",
        "OM - TERATOMA",
        "OM - DISGERMINOMA",
        "OM - CARCINOMA DA VAGINA",
        "OM - CANCRO DA VULVA",
        "OM - DOENÇA DO TROFOBLASTO GESTACIONAL",
        "OM - CARCINOMA DO ENDOMÉTRIO HER 2",
        "OM - MOLA HIDATIFORME",
        "OM - CORIOCARCINOMA",
        "OM - LEIOMIOSSARCOMA UTERINO",
        "OM - SARCOMA DO ESTROMA ENDOMETRIAL BAIXO GRAU",
        "OM - SARCOMA DO ESTROMA ENDOMETRIAL ALTO GRAU",
        "OM - SARCOMA UTERINO INDIFERENCIADO",
        "OM - ADENOSSARCOMA",
        "OM - CARCINOMA SEROSO ALTO GRAU OVÁRIO",
        "OM - CARCINOMA SEROSO BAIXO GRAU OVÁRIO",
        "OM - CARCINOMA DA TROMPA"
    ],
    
    "mama": [
        "OM - MAMA NEOADJUVANTE LUMINAL A",
        "OM - MAMA ADJUVANTE LUMINAL A",
        "OM - MAMA PALIATIVO LUMINAL A PIK3CA",
        "OM - MAMA PALIATIVO LUMINAL A ESR1",
        "OM - MAMA NEOADJUVANTE LUMINAL B",
        "OM - MAMA ADJUVANTE LUMINAL B",
        "OM - MAMA PALIATIVO LUMINAL B",
        "OM - MAMA PALIATIVO LUMINAL B PIK3CA",
        "OM - MAMA PALIATIVO LUMINAL B ESR1",
        "OM - MAMA NEOADJUVANTE TRIPLO NEGATIVO",
        "OM - MAMA ADJUVANTE TRIPLO NEGATIVO",
        "OM - MAMA PALIATIVO TRIPLO NEGATIVO PD-L1 +",
        "OM - MAMA PALIATIVO TRIPLO NEGATIVO",
        "OM - MAMA NEOADJUVANTE HER2 + PURO",
        "OM - MAMA PALIATIVO HER2 + PURO",
        "OM - MAMA PALIATIVO HER2 + PURO",
        "OM - MAMA NEOADJUVANTE HER2+ LUMINAL B",
        "OM - MAMA ADJUVANTE HER2+ LUMINAL B",
        "OM - MAMA PALIATIVO HER2+ LUMINAL B",
        "OM - MAMA ADJUVANTE BRCA POSITIVO",
        "OM - MAMA PALIATIVO BRCA POSITIVO",
        "OM - MAMA - PRIMARIO OCULTO PALIATIVO"
    ],
    "oncologia_pediatrica": [
        "OPED - LEUCEMIA LINFOBLÁSTICA",
        "OPED - LEUCEMIA MIELOIDE AGUDA",
        "OPED - DOENÇAS CRÓNICAS MIELOPROLIFERATICAS",
        "OPED - SINDROME MIELODISPLÁSICO",
        "OPED - OUTRAS LEUCEMIAS NÃO ESPECIFICADAS",
        "OPED - LINFOMA HODGKIN",
        "OPED - LINFOMA NÃO-HODGKIN (EXCEPTO LINFOMA BURKITT)",
        "OPED - LINFOMA BURKITT",
        "OPED - NEOPLASIAS LINFORETICULARES",
        "OPED - LINFOMAS NÃO ESPECIFICADOS",
        "OPED - EPENDIMOMAS",
        "OPED - TUMOR PLEXO CORÓIDE",
        "OPED - ASTROCITOMAS",
        "OPED - TUMOR EMBRIONÁRIO INTRACRANIANO",
        "OPED - TUMOR EMBRIONÁRIO INTRAESPINHAL",
        "OPED - OUTRAS NEOPLASIAS ESPECÍFICAS INTRACRANIANAS",
        "OPED - OUTRAS NEOPLASIAS ESPECÍFICAS INTRAESPINHAL",
        "OPED - OUTROS GLIOMAS",
        "OPED - OUTRAS NEOPLASIAS INESPECÍFICAS INTRACRANIANAS",
        "OPED - OUTRAS NEOPLASIAS INESPECÍFICAS INTRAESPINHAL",
        "OPED - NEUROBLASTOMA",
        "OPED - GANGLIONEUROBLASTOMA",
        "OPED - OUTROS GLIOMAS",
        "OPED - RETINOBLASTOMA",
        "OPED - NEFROBLASTOMA",
        "OPED - OUTROS TUMORES NÃO EPITELIAIS",
        "OPED - CARCINOMAS RENAIS",
        "OPED - TUMORES MALIGNOS RENAIS INESPECÍFICAS",
        "OPED - HEPATOBLASTOMA",
        "OPED - CARCINOMA HEPÁTICO",
        "OPED - TUMORES MALIGNOS HEPÁTICOS INESPECÍFICAS",
        "OPED - OSTEOSSARCOMAS",
        "OPED - CONDROSSARCOMAS",
        "OPED - TUMORES EWING",
        "OPED - TUMORES MALIGNOS DO OSSO ESPECÍFICOS",
        "OPED - TUMORES MALIGNOS DO OSSO INESPECÍFICOS",
        "OPED - RABDOMIOSSARCOMA",
        "OPED - FIBROSSARCOMAS",
        "OPED - TUMORES DA BAINHAS NERVOSAS PERIFÉRICAS",
        "OPED - OUTROS TUMORES FIBROSOS?",
        "OPED - SARCOMA KAPOSI",
        "OPED - OUTROS SARCOMAS DE TECIDOS MOLES",
        "OPED - SARCOMAS TECIDOS MOLES INESPECÍFICOS",
        "OPED - TUMORES DE CÉLULAS GERMINATIVAS INTRACRANIANOS OU INTRAESPINHAIS",
        "OPED - TUMORES MALIGNOS DE CÉLULAS GERMINATIVAS EXTRACRANIANAS E EXTRAGONADAIS",
        "ONPE - TUMOR MALIGNO DE CÉLULAS GONADAIS",
        "OPED - CARCINOMA GONADAIS",
        "OPED - OUTROS TUMORES MALIGNOS INESPECÍFICOS GONADAIS",
        "OPED - CARCINOMAS ADENOCORTICAIS",
        "OPED - CARCINOMAS TIRÓIDE",
        "OPED - CARCINOMAS NASOFARINGE",
        "OPED - MELANOMA MALIGNO",
        "OPED - OUTROS CARCINOMAS"
    ],
    "pele": [
        "PE - MELANOMA UVEAL PALIATIVO",
        "PE - MELANOMA",
        "PE - MELANOMA PALIATIVO",
        "PE - MELANOMA PALIATIVO BRAF V600E",
        "PE - MELANOMA PALIATIVO BRAF WILD TYPE",
        "PE - MELANOMA PALIATIVO NRAS +",
        "PE - MELANOMA PALIATIVO KIT +",
        "PE - CARCINOMA ESPINHOCELULAR",
        "PE - CARCINOMA BASOCELULAR (CBC)",
        "PE - CARCINOMA DE CÉLULAS DE MERKEL",
        "PE - SARCOMA DE KAPOSI",
        "PE - OUTRAS ESPECIFICADAS OU NÃO ESPECIFICADAS",
        "PE - METASTIZAÇÃO CUTÂNEA DE PRIMÁRIO DESCONHECIDO"  
    ],
    "pneumologia": [
        "PN - CNPC - CARCINOMA EPIDERMOIDE PULMAO PD-L1 <50",
        "PN - CNPC - CARCINOMA EPIDERMOIDE PULMAO PD-L1 >50",
        "PN - MESOTELIOMA EPITELIOIDE PLEURA",
        "PN - MESOTELIOMA SARCOMATOIDE PLEURA",
        "PN - TIMOMA MALIGNO",
        "PN - ADENOCARCINOMA PULMAO SOE PD-L1 <50",
        "PN - ADENOCARCINOMA PULMAO SOE PD-L1 >50",
        "PN - ADENOCARCINOMA PULMAO EGFR MUTACOES FREQUENTES",
        "PN - ADENOCARCINOMA PULMAO EGFR MUTACOES RARAS",
        "PN - ADENOCARCINOMA PULMAO EGFR EXAO 20",
        "PN - ADENOCARCINOMA PULMAO",
        "PN - ADENOCARCINOMA PULMAO ALK +",
        "PN - ADENOCARCINOMA PULMAO RET +",
        "PN - ADENOCARCINOMA PULMAO MET SKIPPING 14",
        "PN - ADENOCARCINOMA PULMAO NTRK",
        "PN - ADENOCARCINOMA PULMAO HER2",
        "PN - ADENOCARCINOMA PULMAO KRAS G12C",
        "PN - ADENOCARCINOMA PULMAO KRAS OUTRAS",
        "PN - ADENOCARCINOMA PULMAO BRAF V600E",
        "PN - ADENOCARCINOMA PULMAO BRCA +",
        "PN - ADENOCARCINOMA PULMAO PI3KCA",
        "PN - ADENOCARCINOMA PULMAO ROS1",
        "PN - CARCINOMA ADENOESCAMOSO PULMAO",
        "PN - CARCINOMA PLEOMORFICO PULMAO",
        "PN - CARCINOMA GRANDES CELULAS PULMAO",
        "PN - CPPC - CARCINOMA PEQUENAS CELULAS PULMAO ESTADIO LIMITADO",
        "PN - CPPC - CARCINOMA PEQUENAS CELULAS PULMAO ESTADIO EXTENSO",
        "PN - TUMOR NEUROENDOCRINO GRANDES CELULAS PULMAO",
        "PN - TUMOR NEUROENDOCRINO CARCINOIDE TIPICO",
        "PN - TUMOR NEUROENDOCRINO CARCINOIDE ATIPICO",
        "PN - NEOPLASIA PULMAO SOE",
        "PN - HAMARTOMA PULMAO",
        "PN - METASTIZACAO PULMONAR PRIMARIO OCULTO",
        "PN - MESOTELIOMA BIFÁSICO PLEURA",
        "PN - CARCINOMA TÍMICO",
        "PN - ADENOCARCINOMA PULMAO MET amplificação",
        "PN - CARCINOMA SARCOMATÓIDE PULMAO"
    ],
    "snc": [
        "OM - GLIOBLASTOMA IDH WILD TYPE",
        "OM - ASTROCITOMA GRAU 2",
        "OM - ASTROCITOMA GRAU 3",
        "OM - ASTROCITOMA GRAU 4 IDH MUTADO",
        "OM - OLIGODENDROGLIOMA GRAU 2",
        "OM - OLIGODENDROGLIOMA GRAU 3",
        "OM - MEDULOBLASTOMA",
        "OM - GERMINOMA",
        "OM - MENINGIOMA",
        "OM - GANGLIOGLIOMA"
    ],
    "tne": [
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — PÂNCREAS",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — ESTÔMAGO",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — DUODENO",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — INTESTINO DELGADO",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — CÓLON / RETO",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — APÊNDICE",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — TIMO",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — SUPRA-RENAL (FEOCROMOCITOMA)",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — SUPRA-RENAL (PARAGANGLIOMA MALIGNO)",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — MAMA",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — PRIMÁRIO OCULTO / DESCONHECIDO",
        "OM - NEOPLASIA MALIGNA NEUROENDÓCRINA — LOCALIZAÇÃO NÃO ESPECIFICADA / METASTÁTICA"
    ]
}

KNOWN_FIELDS = {
    # Patient fields
    "age", "ecog_ps", "diagnosis", "stage", "molecular_status",
    "gender", "diagnosis_date", "treatment", "treatment_name",
    "treatment_start_date", "treatment_end_date", "pathology_group",
    "progression_date", "control",

    # Hematology
    "leucocitos", "neutrofilos", "neutrofilos_percent", "linfocitos",
    "linfocitos_percent", "monocitos", "monocitos_percent",
    "eosinofilos", "eosinofilos_percent", "basofilos",
    "basofilos_percent",

    # Red Blood Cells
    "eritrocitos", "hemoglobina", "hematocrito", "vc_medio",
    "hcm", "chcm", "rdw",

    # Platelets
    "plaquetas", "vpm", "plaquetocrito", "pdw",

    # Biochemistry
    "glicose", "azoto_ureico", "creatinina", "sodio", "potassio", 
    "proteinas_totais", "albumina", "calcio", "osmolalidade", 
    "ldh", "ast", "alt", "fosfatase_alcalina", "gama_gt", 
    "bilirrubina_total", "creatina_cinase",
}

DATE_FIELDS = {
    "diagnosis_date",
    "treatment_start_date",
    "treatment_end_date",
    "progression_date",
    "death_date"
}

FIELD_RESOLVER = {
    # Diretos
    "age": lambda p: p.age,
    "gender": lambda p: p.gender,
    "ecog_ps": lambda p: p.ecog_ps,
    "diagnosis": lambda p: p.diagnosis,
    "stage": lambda p: p.stage,
    "molecular_status": lambda p: p.molecular_status,
    "diagnosis_date": lambda p: p.diagnosis_date,
    "control": lambda p: p.control,
    "pathology_group": lambda p: p.pathology_group,

    # Relações
    "treatment_name": lambda p: [t.treatment_name for t in p.treatments.all()],
    "treatment_start_date": lambda p: [t.start_date for t in p.treatments.all()],
    "treatment_end_date": lambda p: [t.end_date for t in p.treatments.all()],

    # Hematology
    "leucocitos": lambda p: get_latest_lab_value(p, "leucocitos"),
    "neutrofilos": lambda p: get_latest_lab_value(p, "neutrofilos"),
    "neutrofilos_percent": lambda p: get_latest_lab_value(p, "neutrofilos_percent"),
    "linfocitos": lambda p: get_latest_lab_value(p, "linfocitos"),
    "linfocitos_percent": lambda p: get_latest_lab_value(p, "linfocitos_percent"),
    "monocitos": lambda p: get_latest_lab_value(p, "monocitos"),
    "monocitos_percent": lambda p: get_latest_lab_value(p, "monocitos_percent"),
    "eosinofilos": lambda p: get_latest_lab_value(p, "eosinofilos"),
    "eosinofilos_percent": lambda p: get_latest_lab_value(p, "eosinofilos_percent"),
    "basofilos": lambda p: get_latest_lab_value(p, "basofilos"),
    "basofilos_percent": lambda p: get_latest_lab_value(p, "basofilos_percent"),

    # Red Blood Cells
    "eritrocitos": lambda p: get_latest_lab_value(p, "eritrocitos"),
    "hemoglobina": lambda p: get_latest_lab_value(p, "hemoglobina"),
    "hematocrito": lambda p: get_latest_lab_value(p, "hematocrito"),
    "vc_medio": lambda p: get_latest_lab_value(p, "vc_medio"),
    "hcm": lambda p: get_latest_lab_value(p, "hcm"),
    "chcm": lambda p: get_latest_lab_value(p, "chcm"),
    "rdw": lambda p: get_latest_lab_value(p, "rdw"),

    # Platelets
    "plaquetas": lambda p: get_latest_lab_value(p, "plaquetas"),
    "vpm": lambda p: get_latest_lab_value(p, "vpm"),
    "plaquetocrito": lambda p: get_latest_lab_value(p, "plaquetocrito"),
    "pdw": lambda p: get_latest_lab_value(p, "pdw"),

    # Biochemistry
    "glicose": lambda p: get_latest_lab_value(p, "glicose"),
    "azoto_ureico": lambda p: get_latest_lab_value(p, "azoto_ureico"),
    "creatinina": lambda p: get_latest_lab_value(p, "creatinina"),
    "sodio": lambda p: get_latest_lab_value(p, "sodio"),
    "potassio": lambda p: get_latest_lab_value(p, "potassio"),
    "proteinas_totais": lambda p: get_latest_lab_value(p, "proteinas_totais"),
    "albumina": lambda p: get_latest_lab_value(p, "albumina"),
    "calcio": lambda p: get_latest_lab_value(p, "calcio"),
    "osmolalidade": lambda p: get_latest_lab_value(p, "osmolalidade"),
    "ldh": lambda p: get_latest_lab_value(p, "ldh"),
    "ast": lambda p: get_latest_lab_value(p, "ast"),
    "alt": lambda p: get_latest_lab_value(p, "alt"),
    "fosfatase_alcalina": lambda p: get_latest_lab_value(p, "fosfatase_alcalina"),
    "gama_gt": lambda p: get_latest_lab_value(p, "gama_gt"),
    "bilirrubina_total": lambda p: get_latest_lab_value(p, "bilirrubina_total"),
    "creatina_cinase": lambda p: get_latest_lab_value(p, "creatina_cinase"),

    # Campos ainda não suportados (futuro)
    "sex": lambda p: None,
    "progression_date": lambda p: None,
    "death_date": lambda p: None,
}

dummy_params_extraction = {
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

dummy_criteria_extraction = {
    "inclusion_criteria": 
        [
            "Age ≥ 18 years.", 
            "Histologically or cytologically confirmed metastatic NSCLC (Stage IV).", 
            "Documented progression after first-line platinum-based chemotherapy combined with anti-PD-1 or anti-PD-L1 therapy.", 
            "ECOG Performance Status 0–1.", 
            "At least one measurable lesion per RECIST 1.1.", 
            "Absolute neutrophil count (ANC) ≥ 1.5 x 10^9/L.", 
            "Platelets ≥ 100 x 10^9/L.", 
            "Hemoglobin ≥ 9 g/dL.", 
            "AST ≤ 2.5 x ULN (≤ 5 x ULN if liver metastases).", 
            "ALT ≤ 2.5 x ULN (≤ 5 x ULN if liver metastases).", 
            "Total bilirubin ≤ 1.5 x ULN.", 
            "Creatinine clearance ≥ 40 mL/min (CKD-EPI formula).", 
            "Women of childbearing potential must have a negative pregnancy test prior to treatment initiation.", 
            "Signed informed consent prior to any study-specific procedure."
        ], 
    "exclusion_criteria": 
        [
            "Known EGFR, ALK, or ROS1 genomic alterations with available approved targeted therapy.", 
            "Untreated or symptomatic brain metastases.", 
            "Active autoimmune disease requiring systemic immunosuppressive therapy.", 
            "Interstitial lung disease or active non-infectious pneumonitis.", 
            "Active infection requiring systemic therapy.", 
            "Prior exposure to LUMITAX.", 
            "Other active invasive malignancy within 3 years (except adequately treated non-melanoma skin cancer or carcinoma in situ)."
        ]
}

dummy_criteria_conversion_flat = {
    "inclusion_criteria": [
        {
            "id": 1,
            "text": "Age ≥ 18 years.",
            "logic": {"field": "age", "operator": ">=", "value": 18}
        },
        {
            "id": 2,
            "text": "Histologically confirmed NSCLC AND Stage IV.",
            "logic": {
                "operator": "AND",
                "conditions": [
                    {"field": "diagnosis", "operator": "=", "value": "NSCLC"},
                    {"field": "stage", "operator": "=", "value": "IV"}
                ]
            }
        },
        {
            "id": 3,
            "text": "ECOG Performance Status 0–1 OR Karnofsky ≥ 80.",
            "logic": {
                "operator": "OR",
                "conditions": [
                    {"field": "ecog_ps", "operator": "<=", "value": 1},
                    {"field": "karnofsky_score", "operator": ">=", "value": 80}
                ]
            }
        },
        {
            "id": 4,
            "text": "Hemoglobin ≥ 9 g/dL.",
            "logic": {"field": "hemoglobina", "operator": ">=", "value": 9}
        },
        {
            "id": 5,
            "text": "Creatinine clearance ≥ 40 mL/min.",
            "logic": {
                "unmapped": True,
                "source_text": "Creatinine clearance ≥ 40 mL/min."
            }
        }
    ],

    "exclusion_criteria": [
        {
            "id": 101,
            "text": "EGFR, ALK, or ROS1 mutation present.",
            "logic": {
                "operator": "OR",
                "conditions": [
                    {"field": "egfr_status", "operator": "=", "value": "positive"},
                    {"field": "alk_status", "operator": "=", "value": "positive"},
                    {"field": "ros1_status", "operator": "=", "value": "positive"}
                ]
            }
        },
        {
            "id": 102,
            "text": "Active infection.",
            "logic": {
                "field": "infection_status",
                "operator": "=",
                "value": "active"
            }
        },
        {
            "id": 103,
            "text": "Autoimmune disease requiring treatment.",
            "logic": {
                "unmapped": True,
                "source_text": "Autoimmune disease requiring treatment."
            }
        },
        {
            "id": 104,
            "text": "Prior exposure to LUMITAX.",
            "logic": {
                "field": "prior_lumitax_exposure",
                "operator": "=",
                "value": True
            }
        }
    ]
}

# Auxiliary functions

def normalize_docs(document, document_content):
    if document.type == Document.DocumentType.CLINICAL_DIARY:
        
        text = normalize_text(document_content)
        
        # Removing Header
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        cleaned = []
        
        skip_patterns = [
            r"^UNIDADE LOCAL DE SAÚDE",
            r"^Diário Clínico$",
            r"^\d{2}-\d{2}-\d{4}",
            r"^(?:Dr|Dra|Dr\(a\))\.?\s+.*",
            r"^Processado por computador",
            r"^Pag\.\s*\d+/\d+",
        ]

        for line in lines:

            should_skip = any(
                re.search(pattern, line, re.IGNORECASE)
                for pattern in skip_patterns
            )

            if not should_skip:
                cleaned.append(line)
                
        text = "\n".join(cleaned)
        
        print(f"[DEBUG] Normalized Diary: {text}")
        
        return text
        
    elif document.type == Document.DocumentType.CLINICAL_TRIAL:

        text = normalize_text(document_content)

        inclusion_match = re.search(
            r"(Inclusion Criteria\s*:?\s*)(.*?)(?=Exclusion Criteria\s*:?)",
            text,
            re.IGNORECASE | re.DOTALL,
        )

        exclusion_match = re.search(
            r"(Exclusion Criteria\s*:?\s*)(.*?)(?=\n(?:Study Plan|Study Design|Investigational Product|Control Product|Study Endpoints|Primary Endpoint|Secondary Endpoints|Safety Endpoints|Follow-Up|Statistical Analysis|References)\b|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )

        if inclusion_match and exclusion_match:

            inclusion_text = inclusion_match.group(2).strip()
            exclusion_text = exclusion_match.group(2).strip()

            text = (
                "Inclusion Criteria:\n"
                f"{inclusion_text}\n\n"
                "Exclusion Criteria:\n"
                f"{exclusion_text}"
            )

        print(f"[DEBUG] Normalized Trial: {text}")

        return text
            
    
def normalize_text(text):
    text = unicodedata.normalize("NFKC", text)
    
    text = re.sub(r"[‐-‒–—]", "-", text)

    text = re.sub(r"[ \t]+", " ", text)

    text = re.sub(r"\r\n?", "\n", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def parse_gender(value):
    if not value:
        return None

    value = value.strip().lower()

    if value in ["male", "m", "masculino"]:
        return True

    if value in ["female", "f", "feminino"]:
        return False

    return None

def serialize_analysis(analysis_qs):

    if not analysis_qs:
        return {}

    result = {}

    for a in analysis_qs:
        result[a.name] = {
            "value": a.value,
            "unit": a.unit
        }

    return result



def load_analysis_json(analysis_content):
    try:
        return json.loads(analysis_content)
    except Exception as e:
        print(f"[WARNING] Failed to parse analysis JSON: {e}")
        return None
    
def get_any(d, *keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default
    
def normalize_percentage(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {
        "value": value,
        "unit": "%"
    }
    

def add_analysis(results, name, data):
    if not data:
        return
    
    print(f"[DEBUG] Adding analysis for {name}: {data}")

    value = data.get("value")
    unit = data.get("unit")

    if value is not None:
        results.append({
            "name": name,
            "value": value,
            "unit": unit
        })

def extract_lab_parameters(analysis_json):
    if not analysis_json:
        return []

    results = []

    try:
        h = analysis_json.get("hematology", {})
        e = analysis_json.get("eritrocitos", {})
        p = analysis_json.get("plaquetas", {})
        b = analysis_json.get("bioquimica", {})

        # Hematology
        add_analysis(results, "leucocitos", h.get("leucocitos"))
        add_analysis(results, "neutrofilos", h.get("neutrofilos"))
        add_analysis(results, "linfocitos", h.get("linfocitos"))
        add_analysis(results, "monocitos", h.get("monocitos"))
        add_analysis(results, "eosinofilos", h.get("eosinofilos"))
        add_analysis(results, "basofilos", h.get("basofilos"))

        # Percentages
        percent = h.get("neutrofilos", {}).get("percentage")
        add_analysis(results, "neutrofilos_percent",  normalize_percentage(percent))
        percent = h.get("linfocitos", {}).get("percentage")
        add_analysis(results, "linfocitos_percent", normalize_percentage(percent))
        percent = h.get("monocitos", {}).get("percentage")
        add_analysis(results, "monocitos_percent", normalize_percentage(percent))
        percent = h.get("eosinofilos", {}).get("percentage")
        add_analysis(results, "eosinofilos_percent", normalize_percentage(percent))
        percent = h.get("basofilos", {}).get("percentage")
        add_analysis(results, "basofilos_percent", normalize_percentage(percent))

        # Eritrocitos
        add_analysis(results, "eritrocitos", e.get("eritrocitos"))
        add_analysis(results, "hemoglobina", e.get("hemoglobina"))
        add_analysis(results, "hematocrito", e.get("hematocrito"))
        add_analysis(results, "vc_medio", e.get("Volume_Corpuscular_Medio"))
        add_analysis(results, "hcm", e.get("Hemoglobina_Corpuscular_Media"))

        chcm = get_any(
            e,
            "C.Hemoglobina_Corpuscular_Media",
            "C_Hemoglobina_Corpuscular_Media"
        )
        add_analysis(results, "chcm", chcm)

        add_analysis(results, "rdw", e.get("Coeficiente_Variação_Eritrócitos"))

        # Plaquetas
        add_analysis(results, "plaquetas", p.get("plaquetas"))
        add_analysis(results, "vpm", p.get("volume_plaquetar_medio"))
        add_analysis(results, "plaquetocrito", p.get("plaquetocrito"))
        add_analysis(results, "pdw", p.get("Coeficiente_Variação_Plaquetas"))

        # Bioquimica
        add_analysis(results, "glicose", b.get("glicose"))
        add_analysis(results, "azoto_ureico", b.get("azoto_ureico"))
        add_analysis(results, "creatinina", b.get("creatinina"))
        add_analysis(results, "sodio", b.get("sodio"))
        add_analysis(results, "potassio", b.get("potassio"))
        add_analysis(results, "proteinas_totais", b.get("proteinas_totais"))
        add_analysis(results, "albumina", b.get("albumina"))
        add_analysis(results, "calcio", b.get("calcio"))
        add_analysis(results, "osmolalidade", b.get("osmolalidade"))
        add_analysis(results, "ldh", b.get("ldh"))
        add_analysis(results, "ast", b.get("ast"))
        add_analysis(results, "alt", b.get("alt"))
        add_analysis(results, "fosfatase_alcalina", b.get("fosfatase_alcalina"))
        add_analysis(results, "gama_gt", b.get("gama_gt"))
        add_analysis(results, "bilirrubina_total", b.get("bilirrubina_total"))
        add_analysis(results, "creatina_cinase", b.get("Creatina_cinase"))

        return results

    except Exception as e:
        print(f"[WARNING] Failed to extract lab parameters: {e}")
        return []


def parse_lab_value(value):
    if not value:
        return None
    
    match = re.search(r"[-+]?\d*\.?\d+", value)
    return float(match.group()) if match else None

def extract_patient_id_from_title(title):
    """
    Expected format:
    inconsistancy-diary_patient_{patientid}_{unique_identifier}.txt/pdf
    """
    pattern = r"inconsistancy-diary_patient_(\d+)_"
    match = re.search(pattern, title)

    if match:
        return match.group(1)
    
    print(f"[WARNING] Could not extract patient_id from title: {title}")
    return None

def get_analysis_for_patient(patient_id):
    if not patient_id:
        return None

    expected_filename = f"analysis_patient_{patient_id}.txt"

    for file in ANALYSIS_FILES:
        if file.name == expected_filename:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"[WARNING] Error reading analysis file {file.name}: {e}")
                return None

    print(f"[WARNING] No analysis file found for patient_id={patient_id}")
    return None

def format_logic(logic):
    if not logic:
        return None

    try:
        if "field" in logic:
            field = logic.get("field", "")
            op = logic.get("operator", "")
            value = logic.get("value", "")

            return f"{field} {op} {value}"

        if "conditions" in logic:
            operator = logic.get("operator", "AND")

            parts = []
            for condition in logic["conditions"]:
                formatted = format_logic(condition)
                if formatted:
                    parts.append(formatted)

            if not parts:
                return None

            return f"({f' {operator} '.join(parts)})"

        return str(logic)

    except Exception as e:
        print("FORMAT ERROR:", e)
        return str(logic)

def load_diagnosis_normalization(paths):
    sheets = {}

    for path in paths:
        df = pd.read_csv(path, header=None)
        df = df.dropna(how="all")

        lines = df[0].tolist()

        if len(lines) < 2:
            continue

        group_name = lines[1].strip()
        terms = [line.strip() for line in lines[2:] if line.strip()]

        sheets[group_name] = [{"term": t} for t in terms]

    return sheets

def format_normalization_context(sheets_data):
    parts = []

    for group, records in sheets_data.items():
        parts.append(f"### {group}")

        for r in records:
            parts.append(f"- {r['term']}")

        parts.append("")

    return "\n".join(parts)


def get_normalization_context():
    cache_key = "diagnosis_normalization_context"

    context = cache.get(cache_key)
    if context:
        return context

    sheets = load_diagnosis_normalization(NORMALIZATION_FILES)
    context = format_normalization_context(sheets)

    cache.set(cache_key, context, timeout=86400)

    return context

def process_condition(condition):

    # GROUP
    if "conditions" in condition:
        return {
            "is_group": True,
            "conditions": [process_condition(c) for c in condition.get("conditions", [])],
            "operator": condition.get("operator", "AND")
        }

    field = condition.get("field", "")

    if field not in KNOWN_FIELDS and field != "":
        field_type = "__custom__"
        custom_field = field
    else:
        field_type = field
        custom_field = ""

    return {
        "is_group": False,
        "field_type": field_type,
        "custom_field": custom_field,
        "operator": condition.get("operator", ""),
        "value": condition.get("value", ""),
        "unit": condition.get("unit", "")
    }

def build_dummy_conversion(criteria_payload):
    converted = {
        "inclusion_criteria": [],
        "exclusion_criteria": []
    }

    # --- Inclusion ---
    dummy_inclusion = dummy_criteria_conversion_flat["inclusion_criteria"]

    for i, item in enumerate(criteria_payload.get("inclusion_criteria", [])):
        dummy_logic = dummy_inclusion[i % len(dummy_inclusion)]["logic"]

        converted["inclusion_criteria"].append({
            "id": item["id"],  
            "text": item["text"],
            "logic": dummy_logic
        })

    # --- Exclusion ---
    dummy_exclusion = dummy_criteria_conversion_flat["exclusion_criteria"]

    for i, item in enumerate(criteria_payload.get("exclusion_criteria", [])):
        dummy_logic = dummy_exclusion[i % len(dummy_exclusion)]["logic"]

        converted["exclusion_criteria"].append({
            "id": item["id"],  
            "text": item["text"],
            "logic": dummy_logic
        })

    return converted

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
        temperature=0
    )
    return completion.choices[0].message.content

def extract_json_from_response(raw_text):
    if not raw_text:
        raise ValueError("Empty model response.")

    cleaned = raw_text.strip()

    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end + 1]
        return json.loads(candidate)

    raise ValueError("No valid JSON object found in model response.")

def split_text_into_chunks(text, max_chars=4000, overlap=50):
    paragraphs = text.split("\n")
    
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) < max_chars:
            current_chunk += para + "\n"
        else:
            chunks.append(current_chunk.strip())
            
            current_chunk = current_chunk[-overlap:] + "\n" + para + "\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

def split_by_sections_trial(text):
    inclusion_match = re.search(
        r'Inclusion Criteria(.*?)(Exclusion Criteria|$)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    exclusion_match = re.search(
        r'Exclusion Criteria(.*)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    inclusion = inclusion_match.group(1).strip() if inclusion_match else ""
    exclusion = exclusion_match.group(1).strip() if exclusion_match else ""

    return inclusion, exclusion
    

def normalize(text):
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'within \d+ .*', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_similar(a, b, threshold=0.92):
    return SequenceMatcher(None, a, b).ratio() > threshold

def deduplicate(criteria_list):
    result = []

    for c in criteria_list:
        if isinstance(c, dict):
            raw_text = c.get("text", "")
        else:
            raw_text = c

        text = normalize(raw_text)

        if not any(
            is_similar(
                text,
                normalize(r.get("text") if isinstance(r, dict) else r)
            )
            for r in result
        ):
            result.append(c)

    return result

def deduplicate_cohort_criteria(criteria_list):
    """
    Deduplicação para critérios com estrutura {"cohort_id": ..., "text": ...}.
    Dois critérios similares mas de cohorts diferentes são entradas distintas.
    """
    result = []

    for c in criteria_list:
        raw_text = c.get("text", "")
        cohort_id = c.get("cohort_id")
        text = normalize(raw_text)

        already_exists = any(
            r.get("cohort_id") == cohort_id and
            is_similar(text, normalize(r.get("text", "")))
            for r in result
        )

        if not already_exists:
            result.append(c)

    return result

def run_json_prompt_pipeline(
    *,
    system_prompt_path,
    user_prompt_path,
    replacements,
    log_label=None,
    max_retries=3,
    enable_chunking=False,
    chunk_key=None,
    max_chars=2000,
    overlap=200
):

    if not enable_chunking:
        return _run_single_prompt(
            system_prompt_path,
            user_prompt_path,
            replacements,
            log_label,
            max_retries
        )

    text = replacements.get(chunk_key)
    if not text:
        raise ValueError("Chunking enabled but chunk_key not found in replacements")

    chunks = split_text_into_chunks(text, max_chars=max_chars, overlap=overlap)

    all_results = []

    for i, chunk in enumerate(chunks):
        print(f"{log_label} - Chunk {i+1}/{len(chunks)}")

        chunk_replacements = replacements.copy()
        chunk_replacements[chunk_key] = chunk

        result = _run_single_prompt(
            system_prompt_path,
            user_prompt_path,
            chunk_replacements,
            log_label=f"{log_label} (chunk {i+1})",
            max_retries=max_retries
        )

        all_results.append(result)

    return merge_results(all_results)

def _run_single_prompt(
    system_prompt_path,
    user_prompt_path,
    replacements,
    log_label,
    max_retries
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
            return extract_json_from_response(result)
        except ValueError as e:
            print(f"[Attempt {attempt}/{max_retries}] Error parsing JSON: {e}")
            print("Raw model output:", result)

    raise ValueError(f"Failed after {max_retries} attempts.")

def merge_results(results):
    merged = {}

    for result in results:
        for key, value in result.items():
            if key not in merged:
                merged[key] = []

            if isinstance(value, list):
                merged[key].extend(value)
            else:
                merged[key] = value 

    for key in merged:
        if isinstance(merged[key], list):
            merged[key] = deduplicate(merged[key])

    return merged

def chunk_criteria_list(criteria_list, batch_size=5):
    for i in range(0, len(criteria_list), batch_size):
        yield criteria_list[i:i + batch_size]

def parameter_extraction_pipeline(document, document_content):
    normalization_context = get_normalization_context()

    return run_json_prompt_pipeline(
        system_prompt_path=SYS_PARAMETER_EXTRACTION_PROMPT_FILE,
        user_prompt_path=PARAMETER_EXTRACTION_PROMPT_FILE,
        replacements={
            "{{DIARY_TEXT}}": document_content,
            "{{DIAGNOSIS_NORMALIZATION}}": normalization_context
        },
        log_label=document.title
    )

def cohort_identification_step(trial, trial_content):
    return run_json_prompt_pipeline(
        system_prompt_path=SYS_TRIAL_STRUCTURE_PROMPT_FILE,
        user_prompt_path=TRIAL_STRUCTURE_PROMPT_FILE,
        replacements={
            "{{TRIAL_TEXT}}": trial_content,
        },
        log_label=trial.title
    )

def criteria_extraction_step(trial, trial_content, cohorts=None):
    if not cohorts:
        return _extract_criteria_no_cohorts(trial, trial_content)
    else:
        return _extract_criteria_with_cohorts(trial, trial_content, cohorts)


def _extract_criteria_no_cohorts(trial, trial_content):
    inclusion_text, exclusion_text = split_by_sections_trial(trial_content)
    if not inclusion_text and not exclusion_text:
        raise ValueError("Could not detect Inclusion/Exclusion sections")

    all_inclusion = []
    all_exclusion = []

    inclusion_chunks = split_text_into_chunks(inclusion_text, max_chars=2000, overlap=100)
    for i, chunk in enumerate(inclusion_chunks):
        print(f"{trial.title} - Inclusion Chunk {i+1}/{len(inclusion_chunks)}")
        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_EXTRACTION_PROMPT_FILE,
            user_prompt_path=CRITERIA_EXTRACTION_PROMPT_FILE,
            replacements={
                "{{TRIAL_TEXT}}": chunk,
                "{{CRITERIA_TYPE}}": "inclusion"
            },
            log_label=f"{trial.title} (inclusion chunk {i+1})"
        )
        all_inclusion.extend(result.get("inclusion_criteria", []))

    exclusion_chunks = split_text_into_chunks(exclusion_text, max_chars=2000, overlap=100)
    for i, chunk in enumerate(exclusion_chunks):
        print(f"{trial.title} - Exclusion Chunk {i+1}/{len(exclusion_chunks)}")
        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_EXTRACTION_PROMPT_FILE,
            user_prompt_path=CRITERIA_EXTRACTION_PROMPT_FILE,
            replacements={
                "{{TRIAL_TEXT}}": chunk,
                "{{CRITERIA_TYPE}}": "exclusion"
            },
            log_label=f"{trial.title} (exclusion chunk {i+1})"
        )
        all_exclusion.extend(result.get("exclusion_criteria", []))

    return {
        "document_id": trial.id,
        "document_title": trial.title,
        "has_cohorts": False,
        "inclusion_criteria": deduplicate(all_inclusion),
        "exclusion_criteria": deduplicate(all_exclusion)
    }


def _extract_criteria_with_cohorts(trial, trial_content, cohorts):

    cohorts_context = "\n".join(
        f"- ID: {c['cohort_id']} | Name: {c['name']}"
        for c in cohorts
    )

    inclusion_text, exclusion_text = split_by_sections_trial(trial_content)
    if not inclusion_text and not exclusion_text:
        raise ValueError("Could not detect Inclusion/Exclusion sections")

    all_inclusion = []
    all_exclusion = []

    for criteria_type, text in [("inclusion", inclusion_text), ("exclusion", exclusion_text)]:
        if not text or not text.strip():
            continue

        print(f"{trial.title} - Cohort-aware single-call ({criteria_type})")

        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_EXTRACTION_COHORT_PROMPT_FILE,
            user_prompt_path=CRITERIA_EXTRACTION_COHORT_PROMPT_FILE,
            replacements={
                "{{TRIAL_TEXT}}": text,
                "{{CRITERIA_TYPE}}": criteria_type,
                "{{COHORTS_CONTEXT}}": cohorts_context,
            },
            log_label=f"{trial.title} cohort-aware ({criteria_type})"
        )

        key = f"{criteria_type}_criteria"
        for criterion in result.get(key, []):
            entry = {
                "cohort_id": criterion.get("cohort_id") if isinstance(criterion, dict) else None,
                "text": criterion.get("text", "") if isinstance(criterion, dict) else criterion
            }
            if criteria_type == "inclusion":
                all_inclusion.append(entry)
            else:
                all_exclusion.append(entry)

    return {
        "document_id": trial.id,
        "document_title": trial.title,
        "has_cohorts": True,
        "inclusion_criteria": deduplicate_cohort_criteria(all_inclusion),
        "exclusion_criteria": deduplicate_cohort_criteria(all_exclusion)
    }
        
def criteria_extraction_step_bp(trial, trial_content):

    inclusion_text, exclusion_text = split_by_sections_trial(trial_content)
    if not inclusion_text and not exclusion_text:
        raise ValueError("Could not detect Inclusion/Exclusion sections")

    all_inclusion = []
    all_exclusion = []

    inclusion_chunks = split_text_into_chunks(inclusion_text, max_chars=2000, overlap=100)

    for i, chunk in enumerate(inclusion_chunks):
        print(f"{trial.title} - Inclusion Chunk {i+1}/{len(inclusion_chunks)}")

        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_EXTRACTION_PROMPT_FILE,
            user_prompt_path=CRITERIA_EXTRACTION_PROMPT_FILE,
            replacements={
                "{{TRIAL_TEXT}}": chunk,
                "{{CRITERIA_TYPE}}": "inclusion"
            },
            log_label=f"{trial.title} (inclusion chunk {i+1})"
        )

        all_inclusion.extend(result.get("inclusion_criteria", []))

    exclusion_chunks = split_text_into_chunks(exclusion_text, max_chars=2000, overlap=100)

    for i, chunk in enumerate(exclusion_chunks):
        print(f"{trial.title} - Exclusion Chunk {i+1}/{len(exclusion_chunks)}")

        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_EXTRACTION_PROMPT_FILE,
            user_prompt_path=CRITERIA_EXTRACTION_PROMPT_FILE,
            replacements={
                "{{TRIAL_TEXT}}": chunk,
                "{{CRITERIA_TYPE}}": "exclusion"
            },
            log_label=f"{trial.title} (exclusion chunk {i+1})"
        )
        
        all_exclusion.extend(result.get("exclusion_criteria", []))

    return {
        "document_id": trial.id,
        "document_title": trial.title,
        "inclusion_criteria": deduplicate(all_inclusion),
        "exclusion_criteria": deduplicate(all_exclusion)
    }

def criteria_conversion_step(criteria_extracted, batch_size=5):

    all_inclusion = []
    all_exclusion = []

    for batch in chunk_criteria_list(criteria_extracted["inclusion_criteria"], batch_size):
        partial_payload = {
            "document_id": criteria_extracted["document_id"],
            "document_title": criteria_extracted["document_title"],
            "inclusion_criteria": batch,
            "exclusion_criteria": []
        }

        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_CONVERSION_PROMPT_FILE,
            user_prompt_path=CRITERIA_CONVERSION_PROMPT_FILE,
            replacements={
                "{{CRITERIA_TEXT}}": json.dumps(partial_payload, ensure_ascii=False)
            },
            log_label="conversion (inclusion batch)"
        )

        all_inclusion.extend(result.get("inclusion_criteria", []))
        
    for batch in chunk_criteria_list(criteria_extracted["exclusion_criteria"], batch_size):
        partial_payload = {
            "document_id": criteria_extracted["document_id"],
            "document_title": criteria_extracted["document_title"],
            "inclusion_criteria": [],
            "exclusion_criteria": batch
        }

        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_CRITERIA_CONVERSION_PROMPT_FILE,
            user_prompt_path=CRITERIA_CONVERSION_PROMPT_FILE,
            replacements={
                "{{CRITERIA_TEXT}}": json.dumps(partial_payload, ensure_ascii=False)
            },
            log_label="conversion (exclusion batch)"
        )

        all_exclusion.extend(result.get("exclusion_criteria", []))

    return {
        "inclusion_criteria": deduplicate(all_inclusion),
        "exclusion_criteria": deduplicate(all_exclusion)
    }
    
def matching_llm(patient, logic):
    
    clinical_diary_content = get_patient_text(patient)
    
    analysis = Analysis.objects.filter(patient=patient)
    
    
    try:
        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_MATCHING_PATIENTS_PROMPT_FILE,
            user_prompt_path=MATCHING_PATIENTS_PROMPT_FILE,
            replacements={
                "{{CLINICAL_DIARY}}": clinical_diary_content,
                "{{CRITERION_TEXT}}": json.dumps(logic),
                "{{ANALYSIS_VALUES}}": json.dumps(serialize_analysis(analysis))
            },
            log_label=f"LLM Matching - Patient {patient.id}"
        )

        return {
            "match": result.get("match", False),
            "justification": result.get(
                "justification",
                "No justification provided."
            )
        }

    except Exception as e:
        print(f"[LLM ERROR] {e}")
        return False
    
def get_patient_text(patient):
    cache_key = f"patient_text:{patient.id}"

    text = cache.get(cache_key)
    if text:
        return text

    text = extract_document_text(patient.document)

    cache.set(cache_key, text, timeout=3600)

    return text 
    
def patient_matching_step(patient, trial, trial_criteria):

    match_obj, _ = Patient_trial_match.objects.get_or_create(
        patient=patient,
        trial=trial,
        defaults={"decision": Patient_trial_match.Decision.INCONCLUSIVE}
    )

    general_criteria = []
    cohort_criteria_map = {}

    for c in trial_criteria:
        if c.cohort is None:
            general_criteria.append(c)
        else:
            cid = c.cohort.id
            if cid not in cohort_criteria_map:
                cohort_criteria_map[cid] = {"cohort": c.cohort, "criteria": []}
            cohort_criteria_map[cid]["criteria"].append(c)
            
    def evaluate_criteria_list(criteria):
        inclusion_results, exclusion_results = [], []
        inclusion_details, exclusion_details = [], []

        for c in criteria:
            logic = c.logic.validated_logic if hasattr(c, "logic") and c.logic else None
            if not logic:
                continue

            evaluation = evaluate_condition(patient, logic)
            auto_result = evaluation["result"]
            justification = evaluation["justification"]
            evaluation_method = evaluation["method"]

            Criterion_evaluation.objects.update_or_create(
                match=match_obj,
                criterion=c,
                defaults={
                    "automatic_result": (
                        Criterion_evaluation.EvaluationChoices.PASS
                        if auto_result
                        else Criterion_evaluation.EvaluationChoices.FAIL
                    ),
                    "evaluation_method": evaluation_method,
                    "llm_justification": justification,
                }
            )

            manual_eval = Criterion_evaluation.objects.filter(
                match=match_obj, criterion=c
            ).first()

            final_result = auto_result
            manual_override = False

            if manual_eval and manual_eval.manual_result:
                manual_override = True
                final_result = (
                    manual_eval.manual_result == Criterion_evaluation.EvaluationChoices.PASS
                )

            detail = {
                "id": c.id,
                "criterion": c.raw_criterion,
                "logic": logic,
                "result": final_result,
                "auto_result": auto_result,
                "manual_override": manual_override,
                "manual_result": manual_eval.manual_result if manual_eval else None,
                "evidences": extract_evidence(patient, logic),
                "evaluation_method": evaluation_method,
                "criterion_type": c.type,
                "llm_justification": justification,
            }

            if c.type == "inclusion":
                inclusion_results.append(final_result)
                inclusion_details.append(detail)
            elif c.type == "exclusion":
                exclusion_results.append(final_result)
                exclusion_details.append(detail)

        return {
            "eligible": all(inclusion_results) and not any(exclusion_results),
            "inclusion_passed": sum(inclusion_results),
            "inclusion_total": len(inclusion_results),
            "exclusion_triggered": sum(exclusion_results),
            "inclusion_details": inclusion_details,
            "exclusion_details": exclusion_details,
        }

    general_result = evaluate_criteria_list(general_criteria)
    general_passes = general_result["eligible"]

    cohort_results = {}
    eligible_cohorts = []

    for cid, data in cohort_criteria_map.items():
        cohort_result = evaluate_criteria_list(data["criteria"])
        cohort_result["cohort_name"] = data["cohort"].name
        cohort_result["cohort_id"] = data["cohort"].cohort_id
        cohort_results[cid] = cohort_result

        if general_passes and cohort_result["eligible"]:
            eligible_cohorts.append({
                "id": cid,
                "cohort_id": data["cohort"].cohort_id,
                "name": data["cohort"].name,
            })

    has_cohorts = bool(cohort_criteria_map)

    if has_cohorts:
        is_eligible = general_passes and bool(eligible_cohorts)
    else:
        is_eligible = general_passes

    return {
        "eligible": is_eligible,
        "inclusion_passed": general_result["inclusion_passed"],
        "inclusion_total": general_result["inclusion_total"],
        "exclusion_triggered": general_result["exclusion_triggered"],
        "inclusion_details": general_result["inclusion_details"],
        "exclusion_details": general_result["exclusion_details"],
        "has_cohorts": has_cohorts,
        "eligible_cohorts": eligible_cohorts,
        "cohort_results": cohort_results,
    }
        
def extract_evidence(patient, logic):
    evidences = []

    if not logic:
        return evidences

    # Simple condition
    if "field" in logic:

        patient_value = get_patient_value(
            patient,
            logic["field"]
        )

        patient_unit = None

        # Laboratory value
        if isinstance(patient_value, dict):
            patient_unit = patient_value.get("unit")
            patient_value = patient_value.get("value")

        evidences.append({
            "field": logic.get("field"),
            "patient_value": patient_value,
            "patient_unit": patient_unit,
            "expected_value": logic.get("value"),
            "expected_unit": logic.get("unit"),
            "operator": logic.get("operator", "").upper()
        })

        return evidences

    # Nested conditions
    if "conditions" in logic:

        for condition in logic["conditions"]:
            evidences.extend(
                extract_evidence(patient, condition)
            )

        return evidences

    return evidences

def parse_possible_list(value):
    
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

    return value

def get_patient_value(patient, field):

    resolver = FIELD_RESOLVER.get(field)

    if not resolver:
        print(f"[UNKNOWN FIELD] {field}")
        return None

    try:
        return resolver(patient)

    except Exception as e:
        print(f"[RESOLVER ERROR] {field}: {e}")
        return None

def get_latest_lab_value(patient, analyte_name):

    analysis = (
        patient.analysis
        .filter(name__iexact=analyte_name)
        .first()
    )

    if not analysis:
        return None

    return {
        "value": analysis.value,
        "unit": analysis.unit,
    }

def safe_float(val):
    try:
        return float(val)
    except:
        return None

def parse_relative_date(value):

    if not isinstance(value, str):
        return None

    value = value.lower().strip()

    try:

        if "years ago" in value:
            n = int(value.split()[0])
            return now().date() - relativedelta(years=n)

        if "months ago" in value:
            n = int(value.split()[0])
            return now().date() - relativedelta(months=n)

        if "weeks ago" in value:
            n = int(value.split()[0])
            return now().date() - relativedelta(weeks=n)

    except:
        return None

    return None

def parse_date(value):

    if not value:
        return None

    formats = [
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b. %d, %Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(str(value), fmt).date()
        except:
            pass

    return None
    
def normalize_value(val):
    num = safe_float(val)
    if num is not None:
        return num
    
    return str(val).lower().strip()

def normalize_unit(unit):
    if not unit:
        return ""

    u = (
        str(unit)
        .lower()
        .replace(" ", "")
        .replace("_", "")
    )

    if u.startswith("x"):
        u = u[1:]

    return u


def evaluate_condition(patient, logic):
    if not logic:
        return {
            "result": True,
            "justification": None,
            "method": None
        }

    # Simple
    if "field" in logic:
        field = logic["field"]
        operator = logic["operator"].upper()
        value = parse_possible_list(logic["value"])
        
        print(f"[DEBUG] field={field}, operator={operator}, value={value}, type={type(value)}")
        
        if isinstance(value, bool):
            value = str(value).lower()

        if field not in KNOWN_FIELDS:
            print(f"[LLM FALLBACK] Field '{field}' not in schema")

            llm_result = matching_llm(patient, logic)

            return {
                "result": llm_result["match"],
                "justification": llm_result["justification"],
                "method": Criterion_evaluation.EvaluationMethod.LLM
            }

        patient_value = get_patient_value(patient, field)
            
        patient_unit = None

        if isinstance(patient_value, dict):
            print("[DEBUG] Is laboratory value:", patient_value)
            patient_unit = patient_value.get("unit")
            patient_value = patient_value.get("value")
            
        print(f"[DEBUG] Patient value for '{field}': {patient_value}")
        
        print(f"[DEBUG] Evaluating: {patient_value} {operator} {value}")    
            
        expected_unit = logic.get("unit")
        
        if field in DATE_FIELDS:

            patient_date = parse_date(patient_value)

            relative_date = parse_relative_date(value)

            if patient_date and relative_date:

                if operator == "<=":
                    
                    return {
                        "result": patient_date <= relative_date,
                        "justification": None,
                        "method": Criterion_evaluation.EvaluationMethod.RULE
                    }

                if operator == ">=":
                    
                    return {
                        "result": patient_date >= relative_date,
                        "justification": None,
                        "method": Criterion_evaluation.EvaluationMethod.RULE
                    }

                if operator == "<":
                    
                    return {
                        "result": patient_date < relative_date,
                        "justification": None,
                        "method": Criterion_evaluation.EvaluationMethod.RULE
                    }

                if operator == ">":
                    
                    return {
                        "result": patient_date > relative_date,
                        "justification": None,
                        "method": Criterion_evaluation.EvaluationMethod.RULE
                    }

        if expected_unit and patient_unit:

            normalized_patient_unit = normalize_unit(patient_unit)
            normalized_expected_unit = normalize_unit(expected_unit)

            if normalized_patient_unit != normalized_expected_unit:
                print(
                    f"[UNIT MISMATCH] "
                    f"Patient unit '{patient_unit}' != "
                    f"Expected '{expected_unit}' "
                    f"for field '{field}'"
                )

                return {
                    "result": False,
                    "justification": None,
                    "method": None
                }

        if patient_value is None:
            return {
                "result": False,
                "justification": None,
                "method": None
            }

        # Normalize lists as strings
        if isinstance(value, str) and "," in value:
            value = [v.strip() for v in value.split(",")]

        if operator in ["=", "=="]:
            return {
                "result": str(patient_value).lower() == str(value).lower(),
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == "!=":
            return {
                "result": str(patient_value).lower() != str(value).lower(),
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == ">=":
            left = safe_float(patient_value)
            right = safe_float(value)

            if left is None or right is None:
                print(
                    f"[INVALID NUMERIC COMPARISON] "
                    f"{patient_value} >= {value}"
                )
                return {
                    "result": False,
                    "justification": None,
                    "method": None
                }
                
            return {
                "result": left >= right,
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == "<=":
            left = safe_float(patient_value)
            right = safe_float(value)

            if left is None or right is None:
                print(
                    f"[INVALID NUMERIC COMPARISON] "
                    f"{patient_value} <= {value}"
                )
                return {
                    "result": False,
                    "justification": None,
                    "method": None
                }
            return {
                "result": left <= right,
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == ">":
            left = safe_float(patient_value)
            right = safe_float(value)

            if left is None or right is None:
                print(
                    f"[INVALID NUMERIC COMPARISON] "
                    f"{patient_value} > {value}"
                )
                return {
                    "result": False,
                    "justification": None,
                    "method": None
                }

            return {
                "result": left > right,
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == "<":
            left = safe_float(patient_value)
            right = safe_float(value)

            if left is None or right is None:
                print(
                    f"[INVALID NUMERIC COMPARISON] "
                    f"{patient_value} < {value}"
                )
                return {
                    "result": False,
                    "justification": None,
                    "method": None
                }

            return {
                "result": left < right,
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == "IN":
            normalized_patient = normalize_value(patient_value)

            if isinstance(value, list):
                normalized_values = [normalize_value(v) for v in value]
            else:
                normalized_values = [normalize_value(value)]

            if isinstance(patient_value, list):
                return {
                    "result": any(normalize_value(v) in normalized_values for v in patient_value),
                    "justification": None,
                    "method": Criterion_evaluation.EvaluationMethod.RULE
                }
            return {
                "result": normalized_patient in normalized_values,
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == "NOT_IN":
            normalized_patient = normalize_value(patient_value)

            if isinstance(value, list):
                normalized_values = [normalize_value(v) for v in value]
            else:
                normalized_values = [normalize_value(value)]

            if isinstance(patient_value, list):
                return {
                    "result": all(normalize_value(v) not in normalized_values for v in patient_value),
                    "justification": None,
                    "method": Criterion_evaluation.EvaluationMethod.RULE
                }
            return {
                "result": normalized_patient not in normalized_values,
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }

        if operator == "CONTAINS":
            normalized_value = str(value).lower()

            if isinstance(patient_value, list):
                return {
                    "result": any(normalized_value in str(v).lower() for v in patient_value),
                    "justification": None,
                    "method": Criterion_evaluation.EvaluationMethod.RULE
                }
            return {
                "result": normalized_value in str(patient_value).lower(),
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            }


        if operator == "NOT_CONTAINS":
            normalized_value = str(value).lower()

            if isinstance(patient_value, list):
                return {
                    "result": all(normalized_value not in str(v).lower() for v in patient_value),
                    "justification": None,
                    "method": Criterion_evaluation.EvaluationMethod.RULE
                } 
            return {
                "result": normalized_value not in str(patient_value).lower(),
                "justification": None,
                "method": Criterion_evaluation.EvaluationMethod.RULE
            } 

        # Fallback
        print(f"[UNKNOWN OPERATOR] {operator}")
        return {
            "result": False,
            "justification": None,
            "method": None
        } 

    # Nested
    if "conditions" in logic:
        operator = logic.get("operator", "AND").upper()

        results = [evaluate_condition(patient, c) for c in logic["conditions"]]

        if operator == "AND":
            final_result = all(r["result"] for r in results)
        elif operator == "OR":
            final_result = any(r["result"] for r in results)
        else:
            print(f"[UNKNOWN LOGIC OPERATOR] {operator}")
            return {
                "result": False,
                "justification": None,
                "method": None
            }

        method = (
            Criterion_evaluation.EvaluationMethod.LLM
            if any(r["method"] == Criterion_evaluation.EvaluationMethod.LLM for r in results)
            else Criterion_evaluation.EvaluationMethod.RULE
        )
        combined_justification = "\n".join(
            r["justification"] for r in results if r["justification"]
        ) or None

        return {
            "result": final_result,
            "justification": combined_justification,
            "method": method
        }

    return {
        "result": False,
        "justification": None,
        "method": None
    } 

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
    

def get_ordered_logic_with_positions(logic_criteria_qs, cohorts):
    if cohorts is None:
        cohorts = []
        
    ordered = []

    for lc in logic_criteria_qs:
        if lc.criterion.type == "inclusion" and lc.criterion.cohort is None:
            ordered.append(lc)

    for cohort in cohorts:
        for lc in logic_criteria_qs:
            if lc.criterion.type == "inclusion" and lc.criterion.cohort_id == cohort.id:
                ordered.append(lc)

    for lc in logic_criteria_qs:
        if lc.criterion.type == "exclusion" and lc.criterion.cohort is None:
            ordered.append(lc)

    for cohort in cohorts:
        for lc in logic_criteria_qs:
            if lc.criterion.type == "exclusion" and lc.criterion.cohort_id == cohort.id:
                ordered.append(lc)

    return {lc.id: i + 1 for i, lc in enumerate(ordered)}

# Create your views here.
def trial_list(request):
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()
    file_type = request.GET.get("file_type", "").strip().lower()
    trial_status = request.GET.get("trial_status", "").strip()
    pathology_group = request.GET.get("pathology_group", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    trials = Document.objects.filter(
        type=Document.DocumentType.CLINICAL_TRIAL
    ).select_related("clinical_trial")

    if search:
        trials = trials.filter(
            Q(title__icontains=search) |
            Q(clinical_trial__study_name__icontains=search)
        )

    if status == "extracted":
        trials = trials.filter(extracted=True)
    elif status == "not_extracted":
        trials = trials.filter(extracted=False)

    if trial_status:
        trials = trials.filter(clinical_trial__status=trial_status)

    if pathology_group:
        trials = trials.filter(clinical_trial__pathology_group=pathology_group)

    if date_from:
        trials = trials.filter(clinical_trial__end_date__gte=date_from)

    if date_to:
        trials = trials.filter(clinical_trial__start_date__lte=date_to)

    trial_data = []
    for trial in trials:
        if "." in trial.title:
            original_name, ext = trial.title.rsplit('.', 1)
            ext = ext.lower()
        else:
            ext = ""

        if file_type and ext != file_type:
            continue

        trial_data.append((trial, ext))

    return render(request, 'trialpilot/trial_list.html', {
        'trial_data': trial_data,
        'search': search,
        'status': status,
        'file_type': file_type,
        'trial_status': trial_status,
        'pathology_group': pathology_group,
        'date_from': date_from,
        'date_to': date_to,
        'pathology_choices': ClinicalTrial.PathologyGroupType.choices,
        'trial_status_choices': ClinicalTrial.TrialStatus.choices,
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
        trial = Document.objects.get(id=trial_id)
        if trial.type != Document.DocumentType.CLINICAL_TRIAL:
            return render(request, 'trialpilot/trial_details.html', {
            'trial': None,
            'clinical_trial': None,
            'cohorts': [],
            'versions': [],
            'matches': [],
            'inclusion_criteria': [],
            'exclusion_criteria': [],
            'error': 'Document is not a clinical trial.'
        })
        trial_content = extract_document_text(trial)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/trial_details.html', {
            'trial': None,
            'clinical_trial': None,
            'cohorts': [],
            'versions': [],
            'matches': [],
            'inclusion_criteria': [],
            'exclusion_criteria': [],
            'error': 'Document not found.'
        })
        
    criteria = Trial_criteria.objects.filter(
        document=trial
    ).select_related("logic").order_by("type", "id")
    
    inclusion_criteria = [c for c in criteria if c.type == "inclusion"]
    exclusion_criteria = [c for c in criteria if c.type == "exclusion"]
    
    for c in criteria:
        try:
            logic_obj = c.logic
            logic_data = logic_obj.validated_logic
            c.formatted_logic = format_logic(logic_data)
            print("RAW LOGIC DATA:", logic_data)

            print("FORMATTED:", c.formatted_logic)
        except ObjectDoesNotExist:
            c.formatted_logic = "No logic available"           
   
    versions = Version.objects.filter(document=trial)
    
    clinical_trial = ClinicalTrial.objects.get(
        document=trial
    )
    
    cohorts = Trial_cohort.objects.filter(
        clinical_trial=clinical_trial
    ).order_by("id")

    for cohort in cohorts:
        cohort.inclusion_count = Trial_criteria.objects.filter(
            cohort=cohort,
            type=Trial_criteria.CriterionType.INCLUSION
        ).count()

        cohort.exclusion_count = Trial_criteria.objects.filter(
            cohort=cohort,
            type=Trial_criteria.CriterionType.EXCLUSION
        ).count()

    matches = Patient_trial_match.objects.filter(
        trial=trial
    ).select_related("patient")

    has_cohorts = cohorts.exists()

    for match in matches:

        inclusion_total = 0
        inclusion_passed = 0
        exclusion_triggered = 0

        inclusion_details = []
        exclusion_details = []

        cohort_results = {}

        evaluations = match.criterion_evaluations.select_related(
            "criterion__cohort"
        )

        for evaluation in evaluations:

            criterion = evaluation.criterion

            result = (
                evaluation.manual_result
                if evaluation.manual_result is not None
                else evaluation.automatic_result
            )

            detail = {
                "criterion": (
                    criterion.validated_criterion
                    or criterion.raw_criterion
                ),
                "result": result,
                "justification": evaluation.llm_justification,
                "manual_override": evaluation.manual_result is not None
            }

            if criterion.cohort is None:
                # Critério geral
                if criterion.type == "inclusion":
                    inclusion_total += 1
                    if result == Criterion_evaluation.EvaluationChoices.PASS:
                        inclusion_passed += 1
                    inclusion_details.append(detail)

                elif criterion.type == "exclusion":
                    if result == Criterion_evaluation.EvaluationChoices.PASS:
                        exclusion_triggered += 1
                    exclusion_details.append(detail)

            else:
                # Critério de cohort
                cid = criterion.cohort.id

                if cid not in cohort_results:
                    cohort_results[cid] = {
                        "cohort_name": criterion.cohort.name,
                        "cohort_id": criterion.cohort.cohort_id,
                        "inclusion_total": 0,
                        "inclusion_passed": 0,
                        "exclusion_triggered": 0,
                        "inclusion_details": [],
                        "exclusion_details": [],
                    }

                if criterion.type == "inclusion":
                    cohort_results[cid]["inclusion_total"] += 1
                    if result == Criterion_evaluation.EvaluationChoices.PASS:
                        cohort_results[cid]["inclusion_passed"] += 1
                    cohort_results[cid]["inclusion_details"].append(detail)

                elif criterion.type == "exclusion":
                    if result == Criterion_evaluation.EvaluationChoices.PASS:
                        cohort_results[cid]["exclusion_triggered"] += 1
                    cohort_results[cid]["exclusion_details"].append(detail)

        # Calcular elegibilidade por cohort
        eligible_cohorts = []
        for cid, data in cohort_results.items():
            cohort_eligible = (
                data["inclusion_passed"] == data["inclusion_total"]
                and data["exclusion_triggered"] == 0
            )
            data["eligible"] = cohort_eligible
            if cohort_eligible:
                eligible_cohorts.append(data["cohort_name"])

        match.inclusion_total = inclusion_total
        match.inclusion_passed = inclusion_passed
        match.exclusion_triggered = exclusion_triggered
        match.inclusion_details = inclusion_details
        match.exclusion_details = exclusion_details
        match.has_cohorts = has_cohorts
        match.cohort_results = cohort_results
        match.eligible_cohorts = eligible_cohorts
    
    return render(request, "trialpilot/trial_details.html", {
        "trial": trial,
        "trial_contents": trial_content,
        "versions": versions,
        "inclusion_criteria": inclusion_criteria,
        "exclusion_criteria": exclusion_criteria,
        "matches": matches,
        "cohorts": cohorts,
        "clinical_trial":clinical_trial
        
    })
    

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
    pathology_group = request.GET.get("pathology_group", "")
    diagnosis = request.GET.get("diagnosis", "")
    
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
    
    if pathology_group:
        patients = patients.filter(
            pathology_group=pathology_group
        )

    if diagnosis:
        patients = patients.filter(
            diagnosis__icontains=diagnosis
        )
    patient_data = []
    for patient in patients:
        treatments = Treatment.objects.filter(patient=patient)
        analysis_qs = Analysis.objects.filter(patient=patient)
        
        patient.json_analysis = json.dumps(serialize_analysis(analysis_qs))

        patient_data.append((patient, treatments))
    for patient in patients:
        print("[PATIENT ANALYSIS]", patient.json_analysis)
    return render(request, 'trialpilot/patient_list.html', {
        'patient_data': patient_data,
        'search': search,
        'stage': stage,
        'molecular_status': molecular_status,
        'diagnosis_options': DIAGNOSIS_OPTIONS
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

def clinical_trial_upload(request):
    if request.method == 'POST':
        form = UploadTrialForm(request.POST, request.FILES)
        
        if not form.is_valid():
            return JsonResponse({
                "success": False,
                "errors": form.errors
            }, status=400)

        try:

            doc_type = (
                Document.DocumentType.CLINICAL_TRIAL 
                if form.cleaned_data['type'] 
                else Document.DocumentType.CLINICAL_DIARY
            )
            
            uploaded_file = form.cleaned_data["file"]
            
            original_name, ext = uploaded_file.name.rsplit('.', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{original_name}_{unique_id}.{ext}"

            # Create document
            document = Document.objects.create(
                title=new_filename,
                type=doc_type
            )

            ClinicalTrial.objects.create(
                document=document,
                study_name=form.cleaned_data["study_name"],
                pathology_group=form.cleaned_data["pathology_group"],
                start_date=form.cleaned_data.get("start_date"),
                end_date=form.cleaned_data.get("end_date"),
                status=form.cleaned_data["status"]
            )
            
            document_save(document, uploaded_file, new_filename, version_id='RAW')

            messages.success(request, f"Clinical trial uploaded successfully.")
            return redirect('trial_list')

        except Exception as e:

            messages.error(request, f"Error uploading clinical trial: {str(e)}")
            return redirect('trial_list')
        

def parameter_extraction(request, diary_id):
    try:
        document = Document.objects.get(id=diary_id)    
    except Document.DoesNotExist:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Document not found.'})
    
    if document.extracted:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'Parameters have already been extracted and validated for this document.'})
    if document.type != Document.DocumentType.CLINICAL_DIARY:
        return render(request, 'trialpilot/diary_parameter-extraction.html', {'error': 'This pipeline only accepts Clinical Diary documents.'})
    else:
        if request.method == 'GET':
            document_content = extract_document_text(document)
        
            if not document_content.strip():
                return render(request, 'trialpilot/diary_parameter-extraction.html', {
                    'error': 'Could not extract readable text from this document.'
                })
            
            patient_id = extract_patient_id_from_title(document.title)
            analysis_content = get_analysis_for_patient(patient_id)
            
            analysis_json = load_analysis_json(analysis_content)
            print("[ANALYSIS JSON]", analysis_json)
            lab_params = extract_lab_parameters(analysis_json)

            lab_dict = {
                item["name"]: item
                for item in lab_params
            }
            
            normalized_document_content = normalize_docs(document, document_content)
            
            extracted_params = parameter_extraction_pipeline(document, normalized_document_content)
            
            #extracted_params = dummy_params_extraction
            dummy = False
            
            if dummy:
                sleep(20)  
            
            extracted_params["lab"] = lab_dict
            
            file_params = ContentFile(json.dumps(extracted_params))

            original_name, ext = document.title.rsplit('.', 1)
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"
            
            document_save(document, file_params, new_filename, 'EXTRACTED')
            
            erythrocyte_fields = [
                ('eritrocitos', 'Erythrocytes'),
                ('hemoglobina', 'Hemoglobin'),
                ('hematocrito', 'Hematocrit'),
                ('vc_medio', 'MCV'),
                ('hcm', 'MCH'),
                ('chcm', 'MCHC'),
                ('rdw', 'RDW'),
            ]
            
            platelet_fields = [
                ('plaquetas', 'Platelets'),
                ('vpm', 'MPV'),
                ('plaquetocrito', 'Plateletcrit'),
                ('pdw', 'PDW'),
            ]

            biochemistry_fields = [
                ('glicose', 'Glucose'),
                ('azoto_ureico', 'Urea'),
                ('creatinina', 'Creatinine'),
                ('sodio', 'Sodium'),
                ('potassio', 'Potassium'),
                ('proteinas_totais', 'Total Proteins'),
                ('albumina', 'Albumin'),
                ('calcio', 'Calcium'),
                ('osmolalidade', 'Osmolality'),
                ('ldh', 'LDH'),
                ('ast', 'AST'),
                ('alt', 'ALT'),
                ('fosfatase_alcalina', 'Alkaline Phosphatase'),
                ('gama_gt', 'GGT'),
                ('bilirrubina_total', 'Bilirubin'),
                ('creatina_cinase', 'CK'),
            ]
            
            hemathology_fields = [
                ('neutrofilos', 'neutrofilos_percent', 'Neutrophils'),
                ('linfocitos', 'linfocitos_percent', 'Lymphocytes'),
                ('monocitos', 'monocitos_percent', 'Monocytes'),
                ('eosinofilos', 'eosinofilos_percent', 'Eosinophils'),
                ('basofilos', 'basofilos_percent', 'Basophils')
            ]
            
            return render(
                request,
                'trialpilot/diary_parameter-extraction.html',
                {
                    "diary": document,
                    "diary_content": document_content,
                    "extracted_params": extracted_params,
                    "erythrocyte_fields": erythrocyte_fields,
                    "platelet_fields": platelet_fields,
                    "biochemistry_fields": biochemistry_fields,
                    "hemathology_fields": hemathology_fields
                }
            )
            
        elif request.method == 'POST':
            corrected_params = request.POST.dict()
            corrected_params.pop("csrfmiddlewaretoken", None)
            
            json_string = json.dumps(corrected_params)
            
            patient = Patient_profile.objects.create(
                document=document,
                age=clean_value(corrected_params.get("age_or_birthdate")),
                gender=clean_value(corrected_params.get("gender")),
                ecog_ps=clean_value(corrected_params.get("ecog_ps")),
                diagnosis=clean_value(corrected_params.get("diagnosis")),
                diagnosis_date=clean_value(corrected_params.get("diagnosis_date")),
                molecular_status=clean_value(corrected_params.get("molecular_status")),
                stage=clean_value(corrected_params.get("stage")),
                pathology_group=clean_value(corrected_params.get("pathology_group")),
                control=clean_value(corrected_params.get("control")),
            )
            
            lab_prefix = "lab_"
            lab_fields = {k: v for k, v in corrected_params.items() if k.startswith(lab_prefix)}

            if lab_fields:

                analyses = []

                grouped = {}

                for key, value in lab_fields.items():
                    clean = key[len(lab_prefix):]

                    base = clean.replace("_percent", "").replace("_unit", "")

                    if base not in grouped:
                        grouped[base] = {}

                    grouped[base][clean] = value

                for base, fields in grouped.items():

                    value = fields.get(base)
                    unit = fields.get(base + "_unit")

                    if value:
                        analyses.append(
                            Analysis(
                                patient=patient,
                                name=base,
                                value=value,
                                unit=unit
                            )
                        )

                    percent = fields.get(base + "_percent")
                    if percent:
                        analyses.append(
                            Analysis(
                                patient=patient,
                                name=base + "_percent",
                                value=percent,
                                unit="%"
                            )
                        )

                Analysis.objects.bulk_create(analyses)
            
            treatment_names = request.POST.getlist("treatment_name[]")
            treatment_start_dates = request.POST.getlist("treatment_start_date[]")
            treatment_end_dates = request.POST.getlist("treatment_end_date[]")

            for i in range(len(treatment_names)):
                if treatment_names[i].strip():
                    Treatment.objects.create(
                        patient=patient,
                        treatment_name=clean_value(treatment_names[i]),
                        start_date=clean_value(treatment_start_dates[i]) if i < len(treatment_start_dates) else None,
                        end_date=clean_value(treatment_end_dates[i]) if i < len(treatment_end_dates) else None,
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

def criteria_extraction(request, trial_id):
    try:
        document = Document.objects.get(id=trial_id)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/trial_criteria-extraction.html', {
            'error': 'Document not found.'
        })

    if document.type != Document.DocumentType.CLINICAL_TRIAL:
        return render(request, 'trialpilot/trial_criteria-extraction.html', {
            'error': 'This pipeline only accepts Clinical Trial documents.'
        })

    document_content = extract_document_text(document)

    if not document_content.strip():
        return render(request, 'trialpilot/trial_criteria-extraction.html', {
            'error': 'Could not extract readable text from this document.'
        })
    elif document.extracted:
        return render(request, 'trialpilot/trial_criteria-extraction.html', {'error': 'Criteria have already been extracted for this document.'})
    else:
        if request.method == 'GET':
            
            normalized_document_content = normalize_docs(document, document_content)
            
            cohort_structure = cohort_identification_step(document, normalized_document_content)
            
            has_cohorts = cohort_structure.get("has_cohorts", False)
            cohorts_data = cohort_structure.get("cohorts", [])
            
            print(f"[DEBUG] Cohort structure: {cohort_structure}")
            print(f"[DEBUG] Has cohorts: {has_cohorts}")
            print(f"[DEBUG] Cohort data: {cohorts_data}")
            
            cohort_map = {}
            
            if has_cohorts and cohorts_data:
                with transaction.atomic():
                    clinical_trial = document.clinical_trial
                    for cohort_data in cohorts_data:
                        cohort_obj = Trial_cohort.objects.create(
                            cohort_id=cohort_data["cohort_id"],
                            clinical_trial=clinical_trial,
                            name=cohort_data["name"],
                            description=cohort_data.get("description","")
                        )
                        
                        cohort_map[cohort_data["cohort_id"]] = cohort_obj
            
            criteria_extracted = criteria_extraction_step(
                document,
                normalized_document_content,
                cohorts=cohorts_data if has_cohorts else None
            )
            
            #criteria_extracted = dummy_criteria_extraction
            dummy = False
            
            if dummy:
                sleep(5)  
            
            parsed_criteria = ContentFile(json.dumps(criteria_extracted, ensure_ascii=False).encode("utf-8"))
            
            print(f"[DEBUG] CRITERIA EXTRACTED: {criteria_extracted}")
            
            original_name, ext = document.title.rsplit('.', 1)
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"
            
            document_save(document, parsed_criteria, new_filename, 'EXTRACTED')
            
            with transaction.atomic():

                inclusion_list = criteria_extracted.get("inclusion_criteria", [])
                exclusion_list = criteria_extracted.get("exclusion_criteria", [])

                for criterion in inclusion_list:
                    if isinstance(criterion, dict):
                        criterion_text = criterion.get("text", "")
                        cohort_obj = cohort_map.get(criterion.get("cohort_id"))
                    else:
                        criterion_text = criterion
                        cohort_obj = None

                    Trial_criteria.objects.create(
                        document=document,
                        cohort=cohort_obj,
                        type=Trial_criteria.CriterionType.INCLUSION,
                        raw_criterion=criterion_text,
                        validated_criterion=criterion_text,
                        validated=False
                    )

                for criterion in exclusion_list:
                    if isinstance(criterion, dict):
                        criterion_text = criterion.get("text", "")
                        cohort_obj = cohort_map.get(criterion.get("cohort_id"))
                    else:
                        criterion_text = criterion
                        cohort_obj = None

                    Trial_criteria.objects.create(
                        document=document,
                        cohort=cohort_obj,
                        type=Trial_criteria.CriterionType.EXCLUSION,
                        raw_criterion=criterion_text,
                        validated_criterion=criterion_text,
                        validated=False
                    )

            inclusion_criteria = Trial_criteria.objects.filter(
                document=document,
                type=Trial_criteria.CriterionType.INCLUSION
            )

            exclusion_criteria = Trial_criteria.objects.filter(
                document=document,
                type=Trial_criteria.CriterionType.EXCLUSION
            )
            
            cohorts = Trial_cohort.objects.filter(
                clinical_trial=document.clinical_trial
            ).order_by('cohort_id') if has_cohorts else []

            return render(request, 'trialpilot/trial_criteria-extraction.html', {
                "trial": document,
                "trial_content": document_content,
                "has_cohorts": has_cohorts,
                "cohorts": cohorts,
                "inclusion_criteria": inclusion_criteria.select_related('cohort'),
                "exclusion_criteria": exclusion_criteria.select_related('cohort'),
            })
        
        elif request.method == 'POST':
            with transaction.atomic():
                for key, value in request.POST.items():
                    if key.startswith("criterion_"):
                        criterion_id = key.split("_")[1]

                        try:
                            criterion = Trial_criteria.objects.get(
                                id=criterion_id,
                                document=document
                            )

                            criterion.validated_criterion = value.strip()
                            criterion.validated = True
                            criterion.save()

                        except Trial_criteria.DoesNotExist:
                            continue
                
                new_inclusions = request.POST.getlist("inclusion[]")
                new_exclusions = request.POST.getlist("exclusion[]")
                
                for text in new_inclusions:
                    if text.strip():
                        Trial_criteria.objects.create(
                            document=document,
                            cohort=None,
                            type=Trial_criteria.CriterionType.INCLUSION,
                            raw_criterion=text.strip(),
                            validated_criterion=text.strip(),
                            validated=True
                        )

                for text in new_exclusions:
                    if text.strip():
                        Trial_criteria.objects.create(
                            document=document,
                            cohort=None,
                            type=Trial_criteria.CriterionType.EXCLUSION,
                            raw_criterion=text.strip(),
                            validated_criterion=text.strip(),
                            validated=True
                        )
                
                for key in request.POST:
                    if key.startswith("new_inclusion_cohort_"):
                        cohort_id = key.replace("new_inclusion_cohort_", "").replace("[]", "")
                        cohort_obj = Trial_cohort.objects.get(id=cohort_id)

                        for text in request.POST.getlist(key):
                            if text.strip():
                                Trial_criteria.objects.create(
                                    document=document,
                                    cohort=cohort_obj,
                                    type=Trial_criteria.CriterionType.INCLUSION,
                                    raw_criterion=text.strip(),
                                    validated_criterion=text.strip(),
                                    validated=True
                                )

                    if key.startswith("new_exclusion_cohort_"):
                        cohort_id = key.replace("new_exclusion_cohort_", "").replace("[]", "")
                        cohort_obj = Trial_cohort.objects.get(id=cohort_id)

                        for text in request.POST.getlist(key):
                            if text.strip():
                                Trial_criteria.objects.create(
                                    document=document,
                                    cohort=cohort_obj,
                                    type=Trial_criteria.CriterionType.EXCLUSION,
                                    raw_criterion=text.strip(),
                                    validated_criterion=text.strip(),
                                    validated=True
                                )
                
                inclusion_criteria = Trial_criteria.objects.filter(
                    document=document,
                    type=Trial_criteria.CriterionType.INCLUSION
                )

                exclusion_criteria = Trial_criteria.objects.filter(
                    document=document,
                    type=Trial_criteria.CriterionType.EXCLUSION
                )

                validated_payload = {
                    "document_id": document.id,
                    "document_title": document.title,
                    "validated_at": timezone.now().isoformat(),
                    "inclusion_criteria": [
                        {
                            "id": criterion.id,
                            "raw_criterion": criterion.raw_criterion,
                            "validated_criterion": criterion.validated_criterion
                        }
                        for criterion in inclusion_criteria
                    ],
                    "exclusion_criteria": [
                        {
                            "id": criterion.id,
                            "raw_criterion": criterion.raw_criterion,
                            "validated_criterion": criterion.validated_criterion
                        }
                        for criterion in exclusion_criteria
                    ]
                }

                file_params = ContentFile(
                    json.dumps(validated_payload, ensure_ascii=False, indent=2).encode("utf-8")
                )

                original_name, ext = document.title.rsplit('.', 1)
                name, old_id = original_name.rsplit('_', 1)
                unique_id = uuid.uuid4().hex
                new_filename = f"{name}_{unique_id}.json"

                document_save(document, file_params, new_filename, 'VALIDATED')

            return redirect('criteria_conversion', trial_id=document.id)
        
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

    validated_criteria = Trial_criteria.objects.filter(document=document).order_by("type", "id")
    

    if document.extracted:
        print("ERROR : Document already extracted, skipping criteria extraction step.")
        return render(request, 'trialpilot/trial_criteria-extraction.html', {'error': 'Criteria have already been extracted for this document.'})
    else:
        if request.method == 'GET':
            
            criteria_payload = {
                "document_id": document.id,
                "document_title": document.title,
                "inclusion_criteria": [
                    {
                        "id": criterion.id,
                        "text": criterion.validated_criterion or criterion.raw_criterion
                    }
                    for criterion in validated_criteria
                    if criterion.type == Trial_criteria.CriterionType.INCLUSION
                ],
                "exclusion_criteria": [
                    {
                        "id": criterion.id,
                        "text": criterion.validated_criterion or criterion.raw_criterion
                    }
                    for criterion in validated_criteria
                    if criterion.type == Trial_criteria.CriterionType.EXCLUSION
                ]
            }
            
            converted_logic = criteria_conversion_step(criteria_payload)
            #converted_logic = build_dummy_conversion(criteria_payload)
            dummy = False
            
            if dummy:
                sleep(5) 
            
            parsed_logic = ContentFile(
                json.dumps(converted_logic, ensure_ascii=False, indent=2).encode("utf-8")
            )

            original_name, ext = document.title.rsplit('.', 1)
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"

            document_save(document, parsed_logic, new_filename, 'CONVERTED')
            
            with transaction.atomic():

                # Inclusion Criteria
                for item in converted_logic.get("inclusion_criteria", []):
                    criterion_id = item.get("id")
                    logic_json = item.get("logic", {})

                    try:
                        criterion = Trial_criteria.objects.get(
                            id=criterion_id,
                            document=document,
                            type=Trial_criteria.CriterionType.INCLUSION
                        )

                        Logic_criteria.objects.create(
                            criterion=criterion,
                            raw_logic=logic_json,
                            validated_logic=logic_json,
                            validated=False
                        )

                    except Trial_criteria.DoesNotExist:
                        print(f"Criterion with ID {criterion_id} not found for inclusion criteria.")
                        continue

                # Exclusion Criteria
                for item in converted_logic.get("exclusion_criteria", []):
                    criterion_id = item.get("id")
                    logic_json = item.get("logic", {})

                    try:
                        criterion = Trial_criteria.objects.get(
                            id=criterion_id,
                            document=document,
                            type=Trial_criteria.CriterionType.EXCLUSION
                        )

                        Logic_criteria.objects.create(
                            criterion=criterion,
                            raw_logic=logic_json,
                            validated_logic=logic_json,
                            validated=False
                        )

                    except Trial_criteria.DoesNotExist:
                        print(f"Criterion with ID {criterion_id} not found for exclusion criteria.")
                        continue

            logic_criteria = Logic_criteria.objects.filter(
                criterion__document=document
            ).select_related("criterion").order_by("criterion__type", "criterion__id")
            
            for logic in logic_criteria:
                data = logic.validated_logic or logic.raw_logic or {}

                logic.group_operator = "AND"
                logic.conditions = []

                if "conditions" in data:
                    logic.group_operator = data.get("operator", "AND")
                    logic.conditions = data.get("conditions", [])

                elif "field" in data:
                    logic.group_operator = "AND"
                    logic.conditions = [data]

                else:
                    logic.conditions = [{
                        "field": "",
                        "operator": "",
                        "value": ""
                    }]

                logic.conditions = [process_condition(c) for c in logic.conditions]
                
            for logic in logic_criteria:
                print(f"Logic for criterion {logic.criterion.id} - {logic.criterion.validated_criterion or logic.criterion.raw_criterion}:")
                print(f"Group Operator: {logic.group_operator}")
                print("Conditions:")
                for condition in logic.conditions:
                    print(json.dumps(condition, indent=2))
                    
            cohorts = Trial_cohort.objects.filter(
                clinical_trial=document.clinical_trial
            ).order_by("cohort_id")

            has_cohorts = cohorts.exists()
            
            criterion_position = get_ordered_logic_with_positions(logic_criteria, cohorts if has_cohorts else None)
            
            logic_criteria_list = sorted(
                logic_criteria,
                key=lambda lc: criterion_position.get(lc.id, 9999)
            )
            return render(request, 'trialpilot/trial_criteria-conversion.html', {
                "trial": document,
                "logic_criteria": logic_criteria_list,
                "has_cohorts": has_cohorts,
                "cohorts": cohorts,
                "criterion_position": criterion_position
            })
            
        elif request.method == 'POST':
            with transaction.atomic():
                for key in request.POST:
                    if key.startswith("logic_"):
                        logic_id = key.split("_")[1]

                        try:
                            logic_obj = Logic_criteria.objects.get(
                                id=logic_id,
                                criterion__document=document
                            )

                            group_operator = request.POST.get(f"group_operator_{logic_id}", "AND")

                            conditions = []
                            i = 1

                            while True:
                                field = request.POST.get(f"field_{logic_id}_{i}")
                                operator = request.POST.get(f"operator_{logic_id}_{i}")
                                value = request.POST.get(f"value_{logic_id}_{i}")
                                unit = request.POST.get(f"unit_{logic_id}_{i}")
                                custom_field = request.POST.get(f"field_custom_{logic_id}_{i}")

                                if field is None:
                                    break

                                if field == "__custom__":
                                    field = custom_field

                                if field or operator or value:
                                    condition_data = {
                                        "field": field,
                                        "operator": operator,
                                        "value": value
                                    }

                                    if unit:
                                        condition_data["unit"] = unit

                                    conditions.append(condition_data)

                                i += 1

                            if len(conditions) == 1:
                                final_logic = conditions[0]
                            else:
                                final_logic = {
                                    "operator": group_operator,
                                    "conditions": conditions
                                }

                            logic_obj.validated_logic = final_logic
                            logic_obj.validated = True
                            logic_obj.save()

                        except Logic_criteria.DoesNotExist:
                            continue
                        except json.JSONDecodeError:
                            continue

                inclusion_logic = Logic_criteria.objects.filter(
                    criterion__document=document,
                    criterion__type=Trial_criteria.CriterionType.INCLUSION
                ).select_related("criterion").order_by("criterion__id")

                exclusion_logic = Logic_criteria.objects.filter(
                    criterion__document=document,
                    criterion__type=Trial_criteria.CriterionType.EXCLUSION
                ).select_related("criterion").order_by("criterion__id")

                validated_payload = {
                    "document_id": document.id,
                    "document_title": document.title,
                    "validated_at": timezone.now().isoformat(),
                    "inclusion_criteria": [
                        {
                            "id": logic.criterion.id,
                            "text": logic.criterion.validated_criterion or logic.criterion.raw_criterion,
                            "logic": logic.validated_logic if logic.validated_logic else logic.raw_logic
                        }
                        for logic in inclusion_logic
                    ],
                    "exclusion_criteria": [
                        {
                            "id": logic.criterion.id,
                            "text": logic.criterion.validated_criterion or logic.criterion.raw_criterion,
                            "logic": logic.validated_logic if logic.validated_logic else logic.raw_logic
                        }
                        for logic in exclusion_logic
                    ]
                }

                file_params = ContentFile(
                    json.dumps(validated_payload, ensure_ascii=False, indent=2).encode("utf-8")
                )

                original_name, ext = document.title.rsplit('.', 1)
                name, old_id = original_name.rsplit('_', 1)
                unique_id = uuid.uuid4().hex
                new_filename = f"{name}_{unique_id}.json"
                
                document.extracted = True
                document.save()

                document_save(document, file_params, new_filename, 'VALIDATED')

                messages.success(request, "Criteria extracted, converted and validated with success. For more details, check the clinical trial's detail page.")
                return redirect('trial_list')
        
def match_patients(request, trial_id):
    try:
        document = Document.objects.get(id=trial_id)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/patient_matching.html',{
            'error': 'Document not found.'
        })
        
    if document.type != Document.DocumentType.CLINICAL_TRIAL:
        return render(request, 'trialpilot/patient_matching.html', {
            'error': 'This pipeline only accepts Clinical Trial Documents.'
        })
    elif not document.extracted:
        return render(request, 'trialpilot/patient_matching.html', {
            'error': 'Criteria must be extracted and validated before matching patients.'
        })
    else:
        if request.method == 'GET':
            trial_criteria = Trial_criteria.objects.filter(document=document).select_related("logic")
            
            trial_details = ClinicalTrial.objects.get(document=document)

            patients = Patient_profile.objects.filter(
                Q(pathology_group=trial_details.pathology_group)
            )
            
            print(f"CRITERIA: {trial_criteria}\nPATIENTS: {patients}")
            
            matches = []
            for patient in patients:
                match_result = patient_matching_step(
                                    patient,
                                    document,
                                    trial_criteria
                                )
                matches.append({
                    'patient': patient,
                    'result': match_result
                })
                
                print(f"Patient {patient.id} - {patient.diagnosis}: Match Result: {match_result}")
            
            eligible_count = sum(1 for m in matches if m["result"]["eligible"])
            ineligible_count = len(matches) - eligible_count
        
            return render(request, 'trialpilot/patient_matching.html', {
                "trial": document,
                "patients": patients,
                "matches": matches,
                "eligible_count": eligible_count,
                "ineligible_count": ineligible_count
            })
            
        elif request.method == 'POST':

            overrides = request.POST.getlist("overrides")

            affected_matches = set()
            overridden_criteria_ids = set() 

            for override_json in overrides:

                try:
                    override = json.loads(override_json)

                    patient_id = int(override["patient_id"])
                    criterion_id = int(override["criterion_id"])
                    decision = override["decision"]

                except Exception as e:
                    print(f"[ERROR] Invalid override: {e}")
                    continue

                patient = Patient_profile.objects.get(id=patient_id)
                criterion = Trial_criteria.objects.get(id=criterion_id)

                match_obj = Patient_trial_match.objects.get(
                    patient=patient,
                    trial=document
                )

                criterion_eval = Criterion_evaluation.objects.get(
                    match=match_obj,
                    criterion=criterion
                )

                criterion_eval.manual_result = decision
                criterion_eval.save()

                overridden_criteria_ids.add(criterion_eval.id) 
                affected_matches.add(match_obj.id)

            remaining_evals = Criterion_evaluation.objects.filter(
                match__trial=document
            ).exclude(id__in=overridden_criteria_ids)

            for ev in remaining_evals:
                ev.manual_result = ev.automatic_result
                ev.save()

            for match_id in affected_matches:

                match_obj = Patient_trial_match.objects.get(id=match_id)

                evaluations = (
                    Criterion_evaluation.objects
                    .filter(match=match_obj)
                    .select_related("criterion")
                )

                inclusion_results = []
                exclusion_results = []

                for evaluation in evaluations:

                    final_result = evaluation.manual_result
                    passed = final_result == Criterion_evaluation.EvaluationChoices.PASS

                    if evaluation.criterion.type == "inclusion":
                        inclusion_results.append(passed)
                    else:
                        exclusion_results.append(passed)

                eligible = all(inclusion_results) and not any(exclusion_results)

                match_obj.decision = (
                    Patient_trial_match.Decision.ELIGIBLE
                    if eligible
                    else Patient_trial_match.Decision.INELIGIBLE
                )

                match_obj.save()

            return redirect("trial_details", trial_id=trial_id)


def index(request):
    # DIARIES
    n_diaries = Document.objects.filter(type=Document.DocumentType.CLINICAL_DIARY).count()
    n_diaries_extracted = Document.objects.filter(type=Document.DocumentType.CLINICAL_DIARY, extracted=True).count()
    n_diaries_pending = n_diaries - n_diaries_extracted
    diary_completion = (n_diaries_extracted / n_diaries * 100) if n_diaries > 0 else 0
    last_five_diaries = Document.objects.filter(type=Document.DocumentType.CLINICAL_DIARY, extracted=False).order_by("-created_at")[:5]
    
    # PATIENTS
    n_patients = Patient_profile.objects.count()
    avg_age = Patient_profile.objects.aggregate(Avg('age'))['age__avg']
    top_diagnoses = (
        Patient_profile.objects.values('diagnosis')
        .annotate(count=Count('id'))
        .order_by('-count')[:3]
    )
    active_treatments = Treatment.objects.filter(end_date__isnull=True).count()
    last_five_patients = Patient_profile.objects.order_by('-created_at')[:5]
    
    # TRIALS
    n_trials = Document.objects.filter(type=Document.DocumentType.CLINICAL_TRIAL).count()
    n_trials_extracted = Document.objects.filter(type=Document.DocumentType.CLINICAL_TRIAL, extracted=True).count()
    n_trials_pending = n_trials - n_trials_extracted
    trial_completion = (n_trials_extracted / n_trials * 100) if n_trials > 0 else 0
    n_matches = Patient_trial_match.objects.count()
    last_trial = Document.objects.filter(type=Document.DocumentType.CLINICAL_TRIAL, extracted=False).order_by("-created_at").first()
    
    return render(request, 'trialpilot/index.html', {
        'n_diaries': n_diaries,
        'n_diaries_extracted': n_diaries_extracted,
        'n_diaries_pending': n_diaries_pending,
        'diary_completion': diary_completion,
        'last_five_diaries': last_five_diaries,
        'n_patients': n_patients,
        'avg_age': avg_age,
        'top_diagnoses': top_diagnoses,
        'active_treatments': active_treatments,
        'last_five_patients': last_five_patients,
        'n_trials': n_trials,
        'n_trials_extracted': n_trials_extracted,
        'n_trials_pending': n_trials_pending,
        'trial_completion': trial_completion,
        'n_matches': n_matches,
        'last_trial': last_trial
    })

def dev_tools(request):
    # BASIC
    n_diaries = Document.objects.filter(type=Document.DocumentType.CLINICAL_DIARY).count()
    n_trials = Document.objects.filter(type=Document.DocumentType.CLINICAL_TRIAL).count()
    n_patients = Patient_profile.objects.count()
    n_versions = Version.objects.count()

    total_docs = Document.objects.count()
    avg_versions = n_versions / total_docs if total_docs > 0 else 0

    # EXTRACTION HEALTH
    extracted_docs = Document.objects.filter(extracted=True).count()
    extraction_rate = (extracted_docs / total_docs * 100) if total_docs > 0 else 0

    docs_no_versions = Document.objects.annotate(v_count=Count('versions')).filter(v_count=0).count()

    # CRITERIA
    total_criteria = Trial_criteria.objects.count()
    validated_criteria = Trial_criteria.objects.filter(validated=True).count()

    logic_total = Logic_criteria.objects.count()
    logic_validated = Logic_criteria.objects.filter(validated=True).count()

    # MATCHING
    total_matches = Patient_trial_match.objects.count()

    eligible = Patient_trial_match.objects.filter(decision="eligible").count()
    ineligible = Patient_trial_match.objects.filter(decision="ineligible").count()
    inconclusive = Patient_trial_match.objects.filter(decision="inconclusive").count()

    deterministic = Patient_trial_match.objects.filter(deterministic_result=True).count()

    return render(request, 'trialpilot/dev_tools.html', {
        'n_diaries': n_diaries,
        'n_patients': n_patients,
        'n_trials': n_trials,
        'n_versions': n_versions,
        'avg_versions': avg_versions,

        'extraction_rate': extraction_rate,
        'docs_no_versions': docs_no_versions,

        'total_criteria': total_criteria,
        'validated_criteria': validated_criteria,
        'logic_total': logic_total,
        'logic_validated': logic_validated,

        'total_matches': total_matches,
        'eligible': eligible,
        'ineligible': ineligible,
        'inconclusive': inconclusive,
        'deterministic': deterministic,
    })