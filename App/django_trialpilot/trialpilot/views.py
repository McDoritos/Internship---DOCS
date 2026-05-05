import ast
import datetime
import uuid
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from httpx import request
from .models import Document, Patient_trial_match, Version, Patient_profile, Treatment, Trial_criteria, Logic_criteria, Analysis
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
import json
import re
from difflib import SequenceMatcher
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
import pandas as pd

GROQ_KEY = os.getenv("GROQ_API_KEY")

# Prompt Files
PARAMETER_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "parameter-extraction_prompt.txt"
SYS_PARAMETER_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "parameter-extraction" / "sys_parameter-extraction_prompt.txt"

CRITERIA_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "criteria-extraction_prompt.txt"
SYS_CRITERIA_EXTRACTION_PROMPT_FILE = Path(settings.BASE_DIR) / "prompts" / "criteria-extraction" / "sys_criteria-extraction_prompt.txt"

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
MODEL = "openai/gpt-oss-120b"
TEMP = 0.7

KNOWN_FIELDS = {
            "age", "ecog_ps", "diagnosis", "stage", "molecular_status",
            "sex", "diagnosis_date", "treatment", "treatment_name",
            "treatment_start_date", "treatment_end_date", "pathology_group",
            "progression_date", "control"
        }

FIELD_RESOLVER = {
    # Diretos
    "age": lambda p: p.age,
    "ecog_ps": lambda p: p.ecog_ps,
    "diagnosis": lambda p: p.diagnosis,
    "stage": lambda p: p.stage,
    "molecular_status": lambda p: p.molecular_status,
    "diagnosis_date": lambda p: p.diagnosis_date,
    "control": lambda p: p.control,

    # Relações (IMPORTANTES)
    "treatment_name": lambda p: [t.treatment_name for t in p.treatments.all()],
    "treatment_start_date": lambda p: [t.start_date for t in p.treatments.all()],
    "treatment_end_date": lambda p: [t.end_date for t in p.treatments.all()],

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
            "logic": {"field": "hemoglobin", "operator": ">=", "value": 9}
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

def serialize_analysis(analysis):
    if not analysis:
        return {}

    return {
        "leucocitos": analysis.leucocitos,
        "neutrofilos": analysis.neutrofilos,
        "neutrofilos_percent": analysis.neutrofilos_percent,
        "linfocitos": analysis.linfocitos,
        "linfocitos_percent": analysis.linfocitos_percent,
        "monocitos": analysis.monocitos,
        "monocitos_percent": analysis.monocitos_percent,
        "eosinofilos": analysis.eosinofilos,
        "eosinofilos_percent": analysis.eosinofilos_percent,
        "basofilos": analysis.basofilos,
        "basofilos_percent": analysis.basofilos_percent,

        "eritrocitos": analysis.eritrocitos,
        "hemoglobina": analysis.hemoglobina,
        "hematocrito": analysis.hematocrito,
        "vc_medio": analysis.vc_medio,
        "hcm": analysis.hcm,
        "chcm": analysis.chcm,
        "rdw": analysis.rdw,

        "plaquetas": analysis.plaquetas,
        "vpm": analysis.vpm,
        "plaquetocrito": analysis.plaquetocrito,
        "pdw": analysis.pdw,

        "glicose": analysis.glicose,
        "azoto_ureico": analysis.azoto_ureico,
        "creatinina": analysis.creatinina,
        "sodio": analysis.sodio,
        "potassio": analysis.potassio,
        "proteinas_totais": analysis.proteinas_totais,
        "albumina": analysis.albumina,
        "calcio": analysis.calcio,
        "osmolalidade": analysis.osmolalidade,
        "ldh": analysis.ldh,
        "ast": analysis.ast,
        "alt": analysis.alt,
        "fosfatase_alcalina": analysis.fosfatase_alcalina,
        "gama_gt": analysis.gama_gt,
        "bilirrubina_total": analysis.bilirrubina_total,
        "creatina_cinase": analysis.creatina_cinase,
    }


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
    
def extract_lab_parameters(analysis_json):
    if not analysis_json:
        return {}

    try:
        h = analysis_json["hematology"]
        e = analysis_json["eritrocitos"]
        p = analysis_json["plaquetas"]
        b = analysis_json["bioquimica"]

        return {
            "leucocitos": h["leucocitos"]["value"],
            "neutrofilos": h["neutrofilos"]["value"],
            "neutrofilos_percent": h["neutrofilos"]["percentage"],
            "linfocitos": h["linfocitos"]["value"],
            "linfocitos_percent": h["linfocitos"]["percentage"],
            "monocitos": h["monocitos"]["value"],
            "monocitos_percent": h["monocitos"]["percentage"],
            "eosinofilos": h["eosinofilos"]["value"],
            "eosinofilos_percent": h["eosinofilos"]["percentage"],
            "basofilos": h["basofilos"]["value"],
            "basofilos_percent": h["basofilos"]["percentage"],

            "eritrocitos": e["eritrocitos"]["value"],
            "hemoglobina": e["hemoglobina"]["value"],
            "hematocrito": e["hematocrito"]["value"],
            "vc_medio": e["Volume_Corpuscular_Medio"]["value"],
            "hcm": e["Hemoglobina_Corpuscular_Media"]["value"],
            "chcm": get_any(e, "C.Hemoglobina_Corpuscular_Media", "C_Hemoglobina_Corpuscular_Media")["value"],
            "rdw": e["Coeficiente_Variação_Eritrócitos"]["value"],
            
            "plaquetas": p["plaquetas"]["value"],
            "vpm": p["volume_plaquetar_medio"]["value"],
            "plaquetocrito": p["plaquetocrito"]["value"],
            "pdw": p["Coeficiente_Variação_Plaquetas"]["value"],

            "glicose": b["glicose"]["value"],
            "azoto_ureico": b["azoto_ureico"]["value"],
            "creatinina": b["creatinina"]["value"],
            "sodio": b["sodio"]["value"],
            "potassio": b["potassio"]["value"],
            "proteinas_totais": b["proteinas_totais"]["value"],
            "albumina": b["albumina"]["value"],
            "calcio": b["calcio"]["value"],
            "osmolalidade": b["osmolalidade"]["value"],
            "ldh": b["ldh"]["value"],
            "ast": b["ast"]["value"],
            "alt": b["alt"]["value"],
            "fosfatase_alcalina": b["fosfatase_alcalina"]["value"],
            "gama_gt": b["gama_gt"]["value"],
            "bilirrubina_total": b["bilirrubina_total"]["value"],
            "creatina_cinase": b["Creatina_cinase"]["value"],
        }

    except KeyError as e:
        print(f"[WARNING] Missing expected lab field: {e}")
        return {}


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
    # Nested (GROUP)
    if "conditions" in condition:
        return {
            "is_group": True,
            "conditions": [process_condition(c) for c in condition.get("conditions", [])],
            "operator": condition.get("operator", "AND")
        }

    # Simple (LEAF)
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
        "value": condition.get("value", "")
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
    
def criteria_extraction_step(trial, trial_content):

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
    
    try:
        result = run_json_prompt_pipeline(
            system_prompt_path=SYS_MATCHING_PATIENTS_PROMPT_FILE,
            user_prompt_path=MATCHING_PATIENTS_PROMPT_FILE,
            replacements={
                "{{CLINICAL_DIARY}}": clinical_diary_content,
                "{{CRITERION_TEXT}}": json.dumps(logic)
            },
            log_label=f"LLM Matching - Patient {patient.id}"
        )

        return result.get("match", False)

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
    
def patient_matching_step(patient, trial_criteria):
    inclusion_results = []
    exclusion_results = []

    inclusion_details = []
    exclusion_details = []

    for c in trial_criteria:
        logic = c.logic.validated_logic
        if not logic:
            continue

        result = evaluate_condition(patient, logic)

        evidences = extract_evidence(patient, logic)

        detail = {
            "criterion": c.raw_criterion,
            "logic": logic,
            "result": result,
            "evidences": evidences
        }

        if c.type == "inclusion":
            inclusion_results.append(result)
            inclusion_details.append(detail)

        elif c.type == "exclusion":
            exclusion_results.append(result)
            exclusion_details.append(detail)

    is_eligible = all(inclusion_results) and not any(exclusion_results)

    return {
        "eligible": is_eligible,
        "inclusion_passed": sum(inclusion_results),
        "inclusion_total": len(inclusion_results),
        "exclusion_triggered": sum(exclusion_results),
        "inclusion_details": inclusion_details,
        "exclusion_details": exclusion_details
    }
    
def extract_evidence(patient, logic):
    evidences = []

    if not logic:
        return evidences

    if "field" in logic:
        patient_value = get_patient_value(patient, logic["field"])

        evidences.append({
            "patient_value": patient_value,
            "expected_value": logic.get("value"),
            "operator": logic.get("operator", "").upper()
        })
        return evidences

    if logic.get("operator") == "AND" and "conditions" in logic:
        for condition in logic["conditions"]:
            evidences.extend(extract_evidence(patient, condition))

        return evidences

    return evidences

def parse_possible_list(value):
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

def safe_float(val):
    try:
        return float(val)
    except:
        return None
    
def normalize_value(val):
    num = safe_float(val)
    if num is not None:
        return num
    
    return str(val).lower().strip()


def evaluate_condition(patient, logic):
    if not logic:
        return True

    # Simple
    if "field" in logic:
        field = logic["field"]
        operator = logic["operator"].upper()
        value = parse_possible_list(logic["value"])

        if field not in KNOWN_FIELDS:
            print(f"[LLM FALLBACK] Field '{field}' not in schema")

            return matching_llm(patient, logic)

        patient_value = get_patient_value(patient, field)

        if patient_value is None:
            return False

        # Normalize lists as strings
        if isinstance(value, str) and "," in value:
            value = [v.strip() for v in value.split(",")]

        if operator in ["=", "=="]:
            return str(patient_value).lower() == str(value).lower()

        if operator == "!=":
            return str(patient_value).lower() != str(value).lower()

        if operator == ">=":
            return safe_float(patient_value) >= safe_float(value)

        if operator == "<=":
            return safe_float(patient_value) <= safe_float(value)

        if operator == ">":
            return safe_float(patient_value) > safe_float(value)

        if operator == "<":
            return safe_float(patient_value) < safe_float(value)

        if operator == "IN":
            normalized_patient = normalize_value(patient_value)

            if isinstance(value, list):
                normalized_values = [normalize_value(v) for v in value]
            else:
                normalized_values = [normalize_value(value)]

            if isinstance(patient_value, list):
                return any(normalize_value(v) in normalized_values for v in patient_value)

            return normalized_patient in normalized_values

        if operator == "NOT_IN":
            normalized_patient = normalize_value(patient_value)

            if isinstance(value, list):
                normalized_values = [normalize_value(v) for v in value]
            else:
                normalized_values = [normalize_value(value)]

            if isinstance(patient_value, list):
                return all(normalize_value(v) not in normalized_values for v in patient_value)

            return normalized_patient not in normalized_values

        if operator == "CONTAINS":
            normalized_value = str(value).lower()

            if isinstance(patient_value, list):
                return any(normalized_value in str(v).lower() for v in patient_value)

            return normalized_value in str(patient_value).lower()


        if operator == "NOT_CONTAINS":
            normalized_value = str(value).lower()

            if isinstance(patient_value, list):
                return all(normalized_value not in str(v).lower() for v in patient_value)

            return normalized_value not in str(patient_value).lower()

        # Fallback
        print(f"[UNKNOWN OPERATOR] {operator}")
        return False

    # Nested
    if "conditions" in logic:
        operator = logic.get("operator", "AND").upper()

        results = [evaluate_condition(patient, c) for c in logic["conditions"]]

        if operator == "AND":
            return all(results)

        if operator == "OR":
            return any(results)

        print(f"[UNKNOWN LOGIC OPERATOR] {operator}")
        return False

    return False

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
            'error': 'Document is not a clinical trial.'
        })
        trial_content = extract_document_text(trial)
    except Document.DoesNotExist:
        return render(request, 'trialpilot/trial_details.html', {
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
    
    matches = Patient_trial_match.objects.filter(
        trial=trial
    ).select_related("patient")
    
    return render(request, "trialpilot/trial_details.html", {
        "trial": trial,
        "trial_contents": trial_content,
        "versions": versions,
        "inclusion_criteria": inclusion_criteria,
        "exclusion_criteria": exclusion_criteria,
        "matches": matches
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
        analysis_obj = Analysis.objects.filter(patient=patient).first()

        patient.json_analysis = json.dumps(serialize_analysis(analysis_obj))

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
            
            patient_id = extract_patient_id_from_title(document.title)
            analysis_content = get_analysis_for_patient(patient_id)
            
            analysis_json = load_analysis_json(analysis_content)
            lab_params = extract_lab_parameters(analysis_json)
            
            extracted_params = parameter_extraction_pipeline(document, document_content)
            
            #extracted_params = dummy_params_extraction
            
            extracted_params["lab"] = lab_params
            
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
                pathology_group=clean_value(corrected_params.get("pathology_group")),
                control=clean_value(corrected_params.get("control")),
            )
            
            lab_prefix = "lab_"

            lab_fields = {k: v for k, v in corrected_params.items() if k.startswith(lab_prefix)}

            if lab_fields:
                Analysis.objects.create(
                    patient=patient,

                    leucocitos=parse_lab_value(lab_fields.get("lab_leucocitos")),
                    
                    neutrofilos=parse_lab_value(lab_fields.get("lab_neutrofilos")),
                    linfocitos=parse_lab_value(lab_fields.get("lab_linfocitos")),
                    monocitos=parse_lab_value(lab_fields.get("lab_monocitos")),
                    eosinofilos=parse_lab_value(lab_fields.get("lab_eosinofilos")),
                    basofilos=parse_lab_value(lab_fields.get("lab_basofilos")),
                    
                    neutrofilos_percent=parse_lab_value(lab_fields.get("lab_neutrofilos_percent")),
                    linfocitos_percent=parse_lab_value(lab_fields.get("lab_linfocitos_percent")),
                    monocitos_percent=parse_lab_value(lab_fields.get("lab_monocitos_percent")),
                    eosinofilos_percent=parse_lab_value(lab_fields.get("lab_eosinofilos_percent")),
                    basofilos_percent=parse_lab_value(lab_fields.get("lab_basofilos_percent")),


                    eritrocitos=parse_lab_value(lab_fields.get("lab_eritrocitos")),
                    hemoglobina=parse_lab_value(lab_fields.get("lab_hemoglobina")),
                    hematocrito=parse_lab_value(lab_fields.get("lab_hematocrito")),
                    vc_medio=parse_lab_value(lab_fields.get("lab_vc_medio")),
                    hcm=parse_lab_value(lab_fields.get("lab_hcm")),
                    chcm=parse_lab_value(lab_fields.get("lab_chcm")),
                    rdw=parse_lab_value(lab_fields.get("lab_rdw")),

                    plaquetas=parse_lab_value(lab_fields.get("lab_plaquetas")),
                    vpm=parse_lab_value(lab_fields.get("lab_vpm")),
                    plaquetocrito=parse_lab_value(lab_fields.get("lab_plaquetocrito")),
                    pdw=parse_lab_value(lab_fields.get("lab_pdw")),

                    glicose=parse_lab_value(lab_fields.get("lab_glicose")),
                    azoto_ureico=parse_lab_value(lab_fields.get("lab_azoto_ureico")),
                    creatinina=parse_lab_value(lab_fields.get("lab_creatinina")),
                    sodio=parse_lab_value(lab_fields.get("lab_sodio")),
                    potassio=parse_lab_value(lab_fields.get("lab_potassio")),
                    proteinas_totais=parse_lab_value(lab_fields.get("lab_proteinas_totais")),
                    albumina=parse_lab_value(lab_fields.get("lab_albumina")),
                    calcio=parse_lab_value(lab_fields.get("lab_calcio")),
                    osmolalidade=parse_lab_value(lab_fields.get("lab_osmolalidade")),
                    ldh=parse_lab_value(lab_fields.get("lab_ldh")),
                    ast=parse_lab_value(lab_fields.get("lab_ast")),
                    alt=parse_lab_value(lab_fields.get("lab_alt")),
                    fosfatase_alcalina=parse_lab_value(lab_fields.get("lab_fosfatase_alcalina")),
                    gama_gt=parse_lab_value(lab_fields.get("lab_gama_gt")),
                    bilirrubina_total=parse_lab_value(lab_fields.get("lab_bilirrubina_total")),
                    creatina_cinase=parse_lab_value(lab_fields.get("lab_creatina_cinase")),
                )
            
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
            #criteria_extracted = criteria_extraction_step(document, document_content)
            
            criteria_extracted = dummy_criteria_extraction 
            
            parsed_criteria = ContentFile(json.dumps(criteria_extracted, ensure_ascii=False).encode("utf-8"))
            
            original_name, ext = document.title.rsplit('.', 1)
            name, old_id = original_name.rsplit('_', 1)
            unique_id = uuid.uuid4().hex
            new_filename = f"{name}_{unique_id}.json"
            
            document_save(document, parsed_criteria, new_filename, 'EXTRACTED')
            
            with transaction.atomic():

                inclusion_list = criteria_extracted.get("inclusion_criteria", [])
                exclusion_list = criteria_extracted.get("exclusion_criteria", [])

                for criterion_text in inclusion_list:
                    Trial_criteria.objects.create(
                        document=document,
                        type=Trial_criteria.CriterionType.INCLUSION,
                        raw_criterion=criterion_text,
                        validated_criterion=criterion_text,
                        validated=False
                    )

                for criterion_text in exclusion_list:
                    Trial_criteria.objects.create(
                        document=document,
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
            
            return render(request, 'trialpilot/trial_criteria-extraction.html',  {
                "trial": document,
                "trial_content": document_content,
                "inclusion_criteria": inclusion_criteria,
                "exclusion_criteria": exclusion_criteria
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
            
            #converted_logic = criteria_conversion_step(criteria_payload)
            converted_logic = build_dummy_conversion(criteria_payload)
            
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
            
            return render(request, 'trialpilot/trial_criteria-conversion.html', {
                "trial": document,
                "logic_criteria": logic_criteria
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
                                custom_field = request.POST.get(f"field_custom_{logic_id}_{i}")

                                if field is None:
                                    break

                                if field == "__custom__":
                                    field = custom_field

                                if field or operator or value:
                                    conditions.append({
                                        "field": field,
                                        "operator": operator,
                                        "value": value
                                    })

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
            
            patients = Patient_profile.objects.all()
            
            print(f"CRITERIA: {trial_criteria}\nPATIENTS: {patients}")
            
            matches = []
            for patient in patients:
                match_result = patient_matching_step(patient, trial_criteria)
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