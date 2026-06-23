"""
Testes Unitários — parameter_extraction view
=============================================
 
  GUARD CLAUSES (GET)
    1. Document não existe
    2. Documento já extraído (extracted=True)
    3. Tipo errado (não é CLINICAL_DIARY)
    4. Ficheiro existe mas está vazio / ilegível
 
  HAPPY PATH (GET)
    5. GET bem-sucedido → pipeline LLM chamado, contexto renderizado com secções corretas
 
  POST — criação de Patient_profile
    6. POST mínimo — cria perfil, redireciona para diary_list
    7. POST com lab fields — cria Analysis corretamente
    8. POST com tratamentos — cria Treatment corretamente
    9. POST com tratamento sem nome não cria registo
   10. POST com múltiplos tratamentos cria todos
   11. Após POST, document.extracted fica True
   12. Após POST, é criada uma Version com status VALIDATED
 
  PIPELINE AUXILIARES
   13. parameter_extraction_pipeline — sem chunking, chama _run_single_prompt uma vez
   14. _run_single_prompt — LLM retorna JSON válido à 1ª tentativa
   15. _run_single_prompt — LLM falha 2x, recupera na 3ª
   16. _run_single_prompt — LLM falha todas as tentativas → ValueError
   17. extract_patient_id_from_title — formato correto extraído
   18. extract_patient_id_from_title — formato errado retorna None
   19. normalize_docs — remove headers do diário clínico
   20. normalize_docs — strip de header de ensaio clínico
   21. load_analysis_json — JSON válido
   22. load_analysis_json — JSON inválido retorna None
 
  LAB PROCESSING (POST)
   23. Grouped lab fields → análises corretas (valor + percentagem)
   24. Lab field sem valor não cria Analysis
"""

import json
import uuid
from io import BytesIO
from unittest.mock import patch, MagicMock, call

from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from trialpilot.models import (
    Document, Patient_profile, Treatment, Analysis, Version
)
from trialpilot.views import (
    parameter_extraction_pipeline,
    _run_single_prompt,
    extract_patient_id_from_title,
    normalize_docs,
    load_analysis_json,
    extract_lab_parameters,
    add_analysis,
)


# HELPERS

SAMPLE_DIARY_CONTENT = """\
UNIDADE LOCAL DE SAÚDE
Diário Clínico
01-01-2024
Dr. João Silva
Processado por computador
Pag. 1/1

Doente do sexo feminino, 55 anos, com diagnóstico de adenocarcinoma do pulmão
estadio IV, EGFR+. ECOG PS 1. Iniciou Osimertinib em Fevereiro de 2023.
Hemoglobina 11.2 g/dL, Leucocitos 6.5 x10^9/L.
"""

SAMPLE_LLM_RESPONSE = json.dumps({
    "age_or_birthdate": 55,
    "gender": "female",
    "ecog_ps": 1,
    "diagnosis": "Adenocarcinoma do pulmão",
    "diagnosis_date": None,
    "molecular_status": "EGFR+",
    "stage": "IV",
    "pathology_group": "pneumologia",
    "control": "Iniciou Osimertinib em Fevereiro de 2023.",
    "treatments": [
        {"name": "Osimertinib", "start_date": "2023-02-01", "end_date": None}
    ]
})

SAMPLE_ANALYSIS_JSON = json.dumps({
    "hematology": {
        "leucocitos": {"value": "6.5", "unit": "x10^9/L"},
        "neutrofilos": {
            "value": "4.0",
            "unit": "x10^9/L",
            "percentage": 61.5
        }
    },
    "eritrocitos": {
        "hemoglobina": {"value": "11.2", "unit": "g/dL"}
    },
    "plaquetas": {},
    "bioquimica": {
        "creatinina": {"value": "0.9", "unit": "mg/dL"}
    }
})


from django.core.files.base import ContentFile


def make_diary_doc(title="inconsistancy-diary_patient_42_abc123.txt", extracted = False):

    doc = Document.objects.create(
        title=title,
        type=Document.DocumentType.CLINICAL_DIARY,
    )

    Version.objects.create(
        document=doc,
        version_name="original",
        file_path=ContentFile(
            SAMPLE_DIARY_CONTENT,
            name=title
        )
    )
    doc.extracted = extracted
    doc.save()
    return doc

# GUARD CLAUSES — GET
# Testing errors paths before reaching the pipeline

class ParameterExtractionGuardClausesTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_nonexistent_document_renders_error(self):
        url = reverse("parameter_extraction", args=[99999])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("not found", response.context["error"].lower())

    @patch("trialpilot.views.extract_document_text", return_value=SAMPLE_DIARY_CONTENT)
    def test_already_extracted_renders_error(self, _mock_text):
        doc = make_diary_doc(extracted=True)
        
        print("EXTRACTED VALUE:", doc.extracted)
        
        url = reverse("parameter_extraction", args=[doc.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("already been extracted", response.context["error"].lower())

    @patch("trialpilot.views.extract_document_text", return_value="some content")
    def test_wrong_document_type_renders_error(self, _mock_text):
        doc = Document.objects.create(
            title="trial_something.pdf",
            type=Document.DocumentType.CLINICAL_TRIAL,
        )
        url = reverse("parameter_extraction", args=[doc.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("clinical diary", response.context["error"].lower())

    @patch("trialpilot.views.extract_document_text", return_value="   ")
    def test_empty_document_content_renders_error(self, _mock_text):
        doc = make_diary_doc()
        url = reverse("parameter_extraction", args=[doc.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("readable text", response.context["error"].lower())


# HAPPY PATH — GET
# Testing the full path with everything mocked

class ParameterExtractionGetHappyPathTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_diary_doc()
        self.url = reverse("parameter_extraction", args=[self.doc.id])

    def _run_get(self, llm_response=SAMPLE_LLM_RESPONSE, analysis_content=SAMPLE_ANALYSIS_JSON):
        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_DIARY_CONTENT), \
             patch("trialpilot.views.get_analysis_for_patient", return_value=analysis_content), \
             patch("trialpilot.views.get_normalization_context", return_value="normalization ctx"), \
             patch("trialpilot.views.call_llm", return_value=llm_response), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys prompt", "{{DIARY_TEXT}} {{DIAGNOSIS_NORMALIZATION}}")), \
             patch("trialpilot.views.document_save"):
            return self.client.get(self.url)

    def test_get_returns_200(self):
        response = self._run_get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trialpilot/diary_parameter-extraction.html")

    def test_get_context_keys_present(self):
        response = self._run_get()
        ctx = response.context

        for key in ["diary", "diary_content", "extracted_params",
                    "erythrocyte_fields", "platelet_fields",
                    "biochemistry_fields", "hemathology_fields"]:
            self.assertIn(key, ctx, f"Missing context key: {key}")


    def test_get_extracted_params_from_llm(self):
        response = self._run_get()
        params = response.context["extracted_params"]

        self.assertEqual(params.get("age_or_birthdate"), 55)
        self.assertEqual(params.get("ecog_ps"), 1)
        self.assertEqual(params.get("stage"), "IV")

    def test_get_lab_values_injected(self):
        response = self._run_get()
        lab = response.context["extracted_params"].get("lab", {})

        # hemoglobina vem do SAMPLE_ANALYSIS_JSON
        self.assertIn("hemoglobina", lab)
        self.assertEqual(lab["hemoglobina"]["value"], "11.2")

    def test_llm_called_exactly_once(self):
        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_DIARY_CONTENT), \
             patch("trialpilot.views.get_analysis_for_patient", return_value=SAMPLE_ANALYSIS_JSON), \
             patch("trialpilot.views.get_normalization_context", return_value="ctx"), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}} {{DIAGNOSIS_NORMALIZATION}}")), \
             patch("trialpilot.views.call_llm", return_value=SAMPLE_LLM_RESPONSE) as mock_llm, \
             patch("trialpilot.views.document_save"):
            self.client.get(self.url)

        mock_llm.assert_called_once()

    def test_get_creates_extracted_version(self):
        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_DIARY_CONTENT), \
             patch("trialpilot.views.get_analysis_for_patient", return_value=SAMPLE_ANALYSIS_JSON), \
             patch("trialpilot.views.get_normalization_context", return_value="ctx"), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}} {{DIAGNOSIS_NORMALIZATION}}")), \
             patch("trialpilot.views.call_llm", return_value=SAMPLE_LLM_RESPONSE), \
             patch("trialpilot.views.document_save") as mock_save:
            self.client.get(self.url)

        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        self.assertEqual(args[3], "EXTRACTED")

    def test_get_no_analysis_file_lab_empty(self):
        response = self._run_get(analysis_content=None)
        lab = response.context["extracted_params"].get("lab", {})
        self.assertEqual(lab, {})

    def test_get_diary_content_is_normalized_before_llm(self):
        captured_prompt = {}

        def fake_llm(sys_prompt, user_prompt):
            captured_prompt["user"] = user_prompt
            return SAMPLE_LLM_RESPONSE

        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_DIARY_CONTENT), \
             patch("trialpilot.views.get_analysis_for_patient", return_value=None), \
             patch("trialpilot.views.get_normalization_context", return_value="ctx"), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}}")), \
             patch("trialpilot.views.call_llm", side_effect=fake_llm), \
             patch("trialpilot.views.document_save"):
            self.client.get(self.url)

        prompt_sent = captured_prompt.get("user", "")

        self.assertNotIn("UNIDADE LOCAL DE SAÚDE", prompt_sent)
        self.assertNotIn("Dr. João Silva", prompt_sent)
        self.assertNotIn("Processado por computador", prompt_sent)

        self.assertIn("adenocarcinoma", prompt_sent)



# POST
# Covers the creation logic on the DB

class ParameterExtractionPostTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_diary_doc()
        self.url = reverse("parameter_extraction", args=[self.doc.id])

    def _post(self, extra_data=None):
        data = {
            "age_or_birthdate": "55",
            "gender": "female",
            "ecog_ps": "1",
            "diagnosis": "Adenocarcinoma do pulmão",
            "diagnosis_date": "2022-01-15",
            "molecular_status": "EGFR+",
            "stage": "IV",
            "pathology_group": "pneumologia",
            "control": "Acompanhamento regular.",
            "treatment_name[]": [],
            "treatment_start_date[]": [],
            "treatment_end_date[]": [],
        }
        if extra_data:
            data.update(extra_data)

        with patch("trialpilot.views.document_save"):
            return self.client.post(self.url, data=data)

    
    def test_post_redirects_to_diary_list(self):
        response = self._post()
        self.assertRedirects(response, reverse("diary_list"))

    def test_post_creates_patient_profile(self):
        self._post()

        patient = Patient_profile.objects.get(document=self.doc)
        self.assertEqual(patient.age, 55)
        self.assertEqual(patient.ecog_ps, 1)
        self.assertEqual(patient.diagnosis, "Adenocarcinoma do pulmão")
        self.assertEqual(patient.stage, "IV")
        self.assertEqual(patient.molecular_status, "EGFR+")
        self.assertEqual(patient.pathology_group, "pneumologia")

    def test_post_sets_document_extracted_true(self):
        self._post()
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.extracted)

    def test_post_creates_validated_version(self):
        with patch("trialpilot.views.document_save") as mock_save:
            self.client.post(self.url, data={
                "age_or_birthdate": "55", "gender": "", "ecog_ps": "1",
                "diagnosis": "X", "diagnosis_date": "", "molecular_status": "",
                "stage": "IV", "pathology_group": "pneumologia", "control": "",
            })

        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        self.assertEqual(args[3], "VALIDATED")

    def test_post_no_treatments_creates_none(self):
        self._post()
        patient = Patient_profile.objects.get(document=self.doc)
        self.assertEqual(Treatment.objects.filter(patient=patient).count(), 0)

    def test_post_single_treatment_created(self):
        response = self._post(extra_data={
            "treatment_name[]": ["Osimertinib"],
            "treatment_start_date[]": ["2023-02-01"],
            "treatment_end_date[]": [""],
        })
        patient = Patient_profile.objects.get(document=self.doc)
        treatments = Treatment.objects.filter(patient=patient)

        self.assertEqual(treatments.count(), 1)
        t = treatments.first()
        self.assertEqual(t.treatment_name, "Osimertinib")
        self.assertEqual(t.start_date.isoformat(), "2023-02-01")
        self.assertIsNone(t.end_date)

    def test_post_multiple_treatments_created(self):
        self._post(extra_data={
            "treatment_name[]": ["Osimertinib", "Pembrolizumab"],
            "treatment_start_date[]": ["2023-02-01", "2024-01-10"],
            "treatment_end_date[]": ["2023-12-31", ""],
        })
        patient = Patient_profile.objects.get(document=self.doc)
        self.assertEqual(Treatment.objects.filter(patient=patient).count(), 2)

    def test_post_blank_treatment_name_skipped(self):
        self._post(extra_data={
            "treatment_name[]": ["", "  "],
            "treatment_start_date[]": ["2023-01-01", ""],
            "treatment_end_date[]": ["", ""],
        })
        patient = Patient_profile.objects.get(document=self.doc)
        self.assertEqual(Treatment.objects.filter(patient=patient).count(), 0)

    def test_post_lab_fields_create_analysis(self):
        self._post(extra_data={
            "lab_hemoglobina": "11.2",
            "lab_hemoglobina_unit": "g/dL",
            "lab_creatinina": "0.9",
            "lab_creatinina_unit": "mg/dL",
        })
        patient = Patient_profile.objects.get(document=self.doc)
        analyses = Analysis.objects.filter(patient=patient)

        names = list(analyses.values_list("name", flat=True))
        self.assertIn("hemoglobina", names)
        self.assertIn("creatinina", names)

        hgb = analyses.get(name="hemoglobina")
        self.assertEqual(hgb.value, 11.2)
        self.assertEqual(hgb.unit, "g/dL")

    def test_post_lab_percent_field_creates_extra_analysis(self):
        self._post(extra_data={
            "lab_neutrofilos": "4.0",
            "lab_neutrofilos_unit": "x10^9/L",
            "lab_neutrofilos_percent": "61.5",
        })
        patient = Patient_profile.objects.get(document=self.doc)
        names = list(Analysis.objects.filter(patient=patient).values_list("name", flat=True))

        self.assertIn("neutrofilos", names)
        self.assertIn("neutrofilos_percent", names)

        pct = Analysis.objects.get(patient=patient, name="neutrofilos_percent")
        self.assertEqual(pct.unit, "%")

    def test_post_lab_field_empty_value_not_created(self):
        self._post(extra_data={
            "lab_albumina": "",       # valor vazio
            "lab_albumina_unit": "g/dL",
        })
        patient = Patient_profile.objects.get(document=self.doc)
        self.assertFalse(Analysis.objects.filter(patient=patient, name="albumina").exists())

    def test_post_none_string_values_cleaned(self):
        self._post(extra_data={
            "ecog_ps": "None",
            "molecular_status": "null",
        })
        patient = Patient_profile.objects.get(document=self.doc)
        self.assertIsNone(patient.ecog_ps)
        self.assertIsNone(patient.molecular_status)


# PIPELINE
# Testing pipeline isolated without the view

class ParameterExtractionPipelineTest(TestCase):

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}} {{DIAGNOSIS_NORMALIZATION}}"))
    @patch("trialpilot.views.call_llm", return_value=SAMPLE_LLM_RESPONSE)
    @patch("trialpilot.views.get_normalization_context", return_value="normalization ctx")
    def test_pipeline_calls_llm_once_without_chunking(self, _mock_ctx, mock_llm, _mock_prompts):
        doc = MagicMock()
        doc.title = "test_diary.txt"

        result = parameter_extraction_pipeline(doc, "some diary text")

        mock_llm.assert_called_once()
        self.assertEqual(result.get("age_or_birthdate"), 55)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}}"))
    @patch("trialpilot.views.call_llm", return_value=SAMPLE_LLM_RESPONSE)
    def test_run_single_prompt_success_first_attempt(self, mock_llm, _mock_prompts):
        result = _run_single_prompt(
            system_prompt_path="fake_sys.txt",
            user_prompt_path="fake_usr.txt",
            replacements={"{{DIARY_TEXT}}": "diary content"},
            log_label="test",
            max_retries=3,
        )
        mock_llm.assert_called_once()
        self.assertEqual(result["age_or_birthdate"], 55)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}}"))
    def test_run_single_prompt_retries_on_bad_json(self, _mock_prompts):
        responses = ["not json", "still bad", SAMPLE_LLM_RESPONSE]

        with patch("trialpilot.views.call_llm", side_effect=responses) as mock_llm:
            result = _run_single_prompt(
                system_prompt_path="fake_sys.txt",
                user_prompt_path="fake_usr.txt",
                replacements={"{{DIARY_TEXT}}": "x"},
                log_label="test",
                max_retries=3,
            )

        self.assertEqual(mock_llm.call_count, 3)
        self.assertEqual(result["age_or_birthdate"], 55)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{DIARY_TEXT}}"))
    @patch("trialpilot.views.call_llm", return_value="totally not json!!!")
    def test_run_single_prompt_raises_after_max_retries(self, mock_llm, _mock_prompts):
        with self.assertRaises(ValueError) as ctx:
            _run_single_prompt(
                system_prompt_path="fake_sys.txt",
                user_prompt_path="fake_usr.txt",
                replacements={"{{DIARY_TEXT}}": "x"},
                log_label="test",
                max_retries=3,
            )

        self.assertEqual(mock_llm.call_count, 3)
        self.assertIn("Failed after 3 attempts", str(ctx.exception))

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "Process: {{DIARY_TEXT}}"))
    def test_run_single_prompt_replaces_placeholder(self, _mock_prompts):
        captured = {}

        def fake_llm(sys_p, user_p):
            captured["prompt"] = user_p
            return SAMPLE_LLM_RESPONSE

        with patch("trialpilot.views.call_llm", side_effect=fake_llm):
            _run_single_prompt(
                system_prompt_path="fake_sys.txt",
                user_prompt_path="fake_usr.txt",
                replacements={"{{DIARY_TEXT}}": "MY DIARY CONTENT"},
                log_label="test",
                max_retries=1,
            )

        self.assertIn("MY DIARY CONTENT", captured["prompt"])
        self.assertNotIn("{{DIARY_TEXT}}", captured["prompt"])

# Auxiliar functions
# auxiliar functions tested isolatedely

class ExtractPatientIdFromTitleTest(TestCase):

    def test_extracts_patient_id_correctly(self):
        title = "inconsistancy-diary_patient_42_abc123xyz.txt"
        self.assertEqual(extract_patient_id_from_title(title), "42")

    def test_extracts_multi_digit_id(self):
        title = "inconsistancy-diary_patient_1234_xyz.pdf"
        self.assertEqual(extract_patient_id_from_title(title), "1234")

    def test_wrong_prefix_returns_none(self):
        title = "diary_patient_99_xxx.txt"
        self.assertIsNone(extract_patient_id_from_title(title))

    def test_no_id_in_title_returns_none(self):
        self.assertIsNone(extract_patient_id_from_title("random_file.txt"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(extract_patient_id_from_title(""))


class NormalizeDocsTest(TestCase):

    def _make_diary_doc(self):
        return Document(
            title="inconsistancy-diary_patient_1_abc.txt",
            type=Document.DocumentType.CLINICAL_DIARY,
        )

    def _make_trial_doc(self):
        return Document(
            title="trial_test.pdf",
            type=Document.DocumentType.CLINICAL_TRIAL,
        )

    def test_diary_removes_header_lines(self):
        doc = self._make_diary_doc()
        result = normalize_docs(doc, SAMPLE_DIARY_CONTENT)

        self.assertNotIn("UNIDADE LOCAL DE SAÚDE", result)
        self.assertNotIn("Diário Clínico", result)
        self.assertNotIn("Processado por computador", result)
        self.assertNotIn("Dr. João Silva", result)
        self.assertNotIn("Pag. 1/1", result)

    def test_diary_preserves_clinical_content(self):
        doc = self._make_diary_doc()
        result = normalize_docs(doc, SAMPLE_DIARY_CONTENT)

        self.assertIn("adenocarcinoma", result.lower())
        self.assertIn("ECOG PS 1", result)


class LoadAnalysisJsonTest(TestCase):

    def test_valid_json_string(self):
        result = load_analysis_json(SAMPLE_ANALYSIS_JSON)
        self.assertIsInstance(result, dict)
        self.assertIn("hematology", result)

    def test_invalid_json_returns_none(self):
        result = load_analysis_json("{invalid json{{")
        self.assertIsNone(result)

    def test_none_input_returns_none(self):
        result = load_analysis_json(None)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        result = load_analysis_json("")
        self.assertIsNone(result)


class ExtractLabParametersTest(TestCase):

    def _parsed_json(self):
        return json.loads(SAMPLE_ANALYSIS_JSON)

    def test_extracts_hemoglobin(self):
        result = extract_lab_parameters(self._parsed_json())
        names = [r["name"] for r in result]
        self.assertIn("hemoglobina", names)

        hgb = next(r for r in result if r["name"] == "hemoglobina")
        self.assertEqual(hgb["value"], "11.2")
        self.assertEqual(hgb["unit"], "g/dL")

    def test_extracts_leucocitos(self):
        result = extract_lab_parameters(self._parsed_json())
        names = [r["name"] for r in result]
        self.assertIn("leucocitos", names)

    def test_extracts_creatinina(self):
        result = extract_lab_parameters(self._parsed_json())
        names = [r["name"] for r in result]
        self.assertIn("creatinina", names)

    def test_extracts_neutrofilos_percent_when_percentage_present(self):
        result = extract_lab_parameters(self._parsed_json())
        names = [r["name"] for r in result]
        self.assertIn("neutrofilos_percent", names)

        pct = next(r for r in result if r["name"] == "neutrofilos_percent")
        self.assertEqual(pct["unit"], "%")

    def test_empty_json_returns_empty_list(self):
        self.assertEqual(extract_lab_parameters({}), [])

    def test_none_returns_empty_list(self):
        self.assertEqual(extract_lab_parameters(None), [])

    def test_missing_sections_returns_empty_list(self):
        self.assertEqual(extract_lab_parameters({"other_section": {}}), [])


class AddAnalysisTest(TestCase):

    def test_adds_entry_with_value(self):
        results = []
        add_analysis(results, "hemoglobina", {"value": "11.2", "unit": "g/dL"})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "hemoglobina")
        self.assertEqual(results[0]["value"], "11.2")
        self.assertEqual(results[0]["unit"], "g/dL")

    def test_skips_none_data(self):
        results = []
        add_analysis(results, "hemoglobina", None)
        self.assertEqual(len(results), 0)

    def test_skips_entry_with_none_value(self):
        results = []
        add_analysis(results, "hemoglobina", {"value": None, "unit": "g/dL"})
        self.assertEqual(len(results), 0)

    def test_skips_empty_dict(self):
        results = []
        add_analysis(results, "hemoglobina", {})
        self.assertEqual(len(results), 0)

    def test_unit_can_be_none(self):
        results = []
        add_analysis(results, "ecog_ps", {"value": "1", "unit": None})
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0]["unit"])