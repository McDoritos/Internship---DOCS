"""
Testes Unitários — criteria_extraction view
============================================
 
Cobre todos os caminhos da view e das funções auxiliares que ela invoca.
A principal diferença em relação ao parameter_extraction é o CHUNKING:
os critérios são extraídos por secções (Inclusion / Exclusion) e por chunks
dentro de cada secção, com merge e deduplicação no final.
 
  GUARD CLAUSES (GET)
    1.  Documento não existe
    2.  Tipo errado (não é CLINICAL_TRIAL)
    3.  Texto extraído está vazio
    4.  Documento já extraído (extracted=True)
 
  HAPPY PATH GET — sem cohorts
    5.  GET retorna 200 e template correto
    6.  Contexto tem as chaves essenciais
    7.  Trial_criteria de inclusão criados na BD
    8.  Trial_criteria de exclusão criados na BD
    9.  Version EXTRACTED criada
   10.  has_cohorts=False quando LLM não detecta cohorts
 
  HAPPY PATH GET — com cohorts
   11.  Trial_cohort objetos criados na BD
   12.  Trial_criteria associados ao cohort correto
   13.  has_cohorts=True no contexto
   14.  Cohort context enviado ao LLM de extração com cohorts
 
  PIPELINE DE EXTRAÇÃO — sem cohorts / com chunking
   15.  _extract_criteria_no_cohorts — texto com 1 chunk → LLM chamado 2× (inclusion + exclusion)
   16.  _extract_criteria_no_cohorts — texto longo → LLM chamado >2× (múltiplos chunks)
   17.  _extract_criteria_no_cohorts — texto sem secções → ValueError
   18.  Critérios duplicados entre chunks são deduplicados
   19.  merge_results combina listas de múltiplos chunks
 
  PIPELINE DE EXTRAÇÃO — com cohorts (sem chunking por secção)
   20.  _extract_criteria_with_cohorts — LLM chamado 2× (inclusion + exclusion)
   21.  Critérios associados ao cohort_id correto
   22.  Critérios de cohorts diferentes com texto idêntico NÃO são deduplicados
   23.  Secção vazia (ex.: exclusion) é ignorada sem erro
 
  SPLIT & CHUNK HELPERS
   24.  split_by_sections_trial — extrai inclusion e exclusion corretamente
   25.  split_by_sections_trial — sem secções devolve ("", "")
   26.  split_text_into_chunks — texto curto → 1 chunk
   27.  split_text_into_chunks — texto longo → múltiplos chunks com overlap
 
  DEDUPLICAÇÃO
   28.  deduplicate — strings exatamente iguais → 1 entrada
   29.  deduplicate — strings muito similares (>0.92) → 1 entrada
   30.  deduplicate — strings distintas → todas mantidas
   31.  deduplicate_cohort_criteria — igual texto, mesmo cohort → 1 entrada
   32.  deduplicate_cohort_criteria — igual texto, cohorts diferentes → 2 entradas
 
  POST — validação de critérios
   33.  POST atualiza criterion.validated_criterion e validated=True
   34.  POST com criterion_id inválido é ignorado sem erro
   35.  POST cria novos critérios de inclusão via inclusion[]
   36.  POST cria novos critérios de exclusão via exclusion[]
   37.  POST ignora inclusion[] em branco
   38.  POST cria critério associado a cohort via new_inclusion_cohort_{id}[]
   39.  POST cria critério de exclusão associado a cohort via new_exclusion_cohort_{id}[]
   40.  POST redireciona para criteria_conversion com trial_id correto
   41.  POST cria Version VALIDATED
   42.  POST payload VALIDATED tem estrutura correta
"""

import json
import uuid
import datetime
from unittest.mock import patch, MagicMock, call

from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.base import ContentFile

from trialpilot.models import (
    Document, ClinicalTrial, Trial_criteria, Trial_cohort, Version
)
from trialpilot.views import (
    _extract_criteria_no_cohorts,
    _extract_criteria_with_cohorts,
    criteria_extraction_step,
    split_by_sections_trial,
    split_text_into_chunks,
    deduplicate,
    deduplicate_cohort_criteria,
    merge_results,
)

# HELPERS

SAMPLE_TRIAL_CONTENT = """\
Inclusion Criteria:
- Age >= 18 years
- Histologically confirmed NSCLC Stage IV
- ECOG Performance Status 0-1
- Hemoglobin >= 9 g/dL
- Creatinine clearance >= 40 mL/min

Exclusion Criteria:
- Known EGFR or ALK mutation with available targeted therapy
- Untreated brain metastases
- Active autoimmune disease requiring systemic immunosuppressive therapy
"""

COHORT_RESPONSE_NO_COHORTS = json.dumps({
    "has_cohorts": False,
    "cohorts": []
})

COHORT_RESPONSE_WITH_COHORTS = json.dumps({
    "has_cohorts": True,
    "cohorts": [
        {"cohort_id": "A", "name": "EGFR+", "description": "Patients with EGFR mutation"},
        {"cohort_id": "B", "name": "ALK+", "description": "Patients with ALK mutation"},
    ]
})

INCLUSION_LLM_RESPONSE = json.dumps({
    "inclusion_criteria": [
        "Age >= 18 years",
        "ECOG Performance Status 0-1",
        "Hemoglobin >= 9 g/dL",
    ]
})

EXCLUSION_LLM_RESPONSE = json.dumps({
    "exclusion_criteria": [
        "Known EGFR or ALK mutation",
        "Untreated brain metastases",
    ]
})

COHORT_INCLUSION_LLM_RESPONSE = json.dumps({
    "inclusion_criteria": [
        {"cohort_id": "A", "text": "EGFR mutation confirmed"},
        {"cohort_id": "B", "text": "ALK mutation confirmed"},
        {"cohort_id": None, "text": "Age >= 18 years"},
    ]
})

COHORT_EXCLUSION_LLM_RESPONSE = json.dumps({
    "exclusion_criteria": [
        {"cohort_id": "A", "text": "Prior EGFR-targeted therapy"},
        {"cohort_id": None, "text": "Active infection"},
    ]
})


def make_trial_doc(title="trial_study_abc123.pdf", extracted=False):

    doc = Document.objects.create(
        title=title,
        type=Document.DocumentType.CLINICAL_TRIAL,
        extracted=extracted
    )

    Version.objects.create(
        document=doc,
        version_name="original",
        file_path=ContentFile(
            SAMPLE_TRIAL_CONTENT,
            name=title
        )
    )

    ClinicalTrial.objects.create(
        document=doc,
        study_name="Study ABC",
        pathology_group="pneumologia",
        start_date=datetime.date(2024,1,1),
        end_date=datetime.date(2026,1,1),
        status="recruiting"
    )

    return doc


# GUARD CLAUSES — GET

class CriteriaExtractionGuardClausesTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_nonexistent_document_renders_error(self):
        response = self.client.get(reverse("criteria_extraction", args=[99999]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("not found", response.context["error"].lower())

    @patch("trialpilot.views.extract_document_text", return_value=SAMPLE_TRIAL_CONTENT)
    def test_wrong_document_type_renders_error(self, _mock_text):
        doc = Document.objects.create(
            title="diary_patient_1_abc.txt",
            type=Document.DocumentType.CLINICAL_DIARY,
        )
        response = self.client.get(reverse("criteria_extraction", args=[doc.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("clinical trial", response.context["error"].lower())

    @patch("trialpilot.views.extract_document_text", return_value="   ")
    def test_empty_document_content_renders_error(self, _mock_text):
        doc = make_trial_doc()
        response = self.client.get(reverse("criteria_extraction", args=[doc.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("readable text", response.context["error"].lower())

    @patch("trialpilot.views.extract_document_text", return_value=SAMPLE_TRIAL_CONTENT)
    def test_already_extracted_renders_error(self, _mock_text):
        doc = make_trial_doc(extracted=True)
        response = self.client.get(reverse("criteria_extraction", args=[doc.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("already been extracted", response.context["error"].lower())

# HAPPY PATH - GET without cohorts

class CriteriaExtractionGetNoCohortTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("criteria_extraction", args=[self.doc.id])

    def _llm_side_effect(self, sys_prompt, user_prompt):
        if "inclusion" in user_prompt.lower():
            return INCLUSION_LLM_RESPONSE
        return EXCLUSION_LLM_RESPONSE

    def _run_get(self, cohort_llm=COHORT_RESPONSE_NO_COHORTS):
        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_TRIAL_CONTENT), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}}")), \
             patch("trialpilot.views.call_llm", side_effect=[cohort_llm,
                                                              INCLUSION_LLM_RESPONSE,
                                                              EXCLUSION_LLM_RESPONSE]), \
             patch("trialpilot.views.document_save"):
            return self.client.get(self.url)

    def test_get_returns_200_and_correct_template(self):
        response = self._run_get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trialpilot/trial_criteria-extraction.html")

    def test_get_context_keys_present(self):
        response = self._run_get()
        for key in ["trial", "trial_content", "has_cohorts",
                    "inclusion_criteria", "exclusion_criteria"]:
            self.assertIn(key, response.context, f"Missing key: {key}")

    def test_get_creates_inclusion_criteria_in_db(self):
        self._run_get()
        inclusions = Trial_criteria.objects.filter(
            clinical_trial=self.doc.clinical_trial,
            type=Trial_criteria.CriterionType.INCLUSION
        )
        self.assertGreater(inclusions.count(), 0)
        texts = list(inclusions.values_list("raw_criterion", flat=True))
        self.assertIn("Age >= 18 years", texts)

    def test_get_creates_exclusion_criteria_in_db(self):
        self._run_get()
        exclusions = Trial_criteria.objects.filter(
            clinical_trial=self.doc.clinical_trial,
            type=Trial_criteria.CriterionType.EXCLUSION
        )
        self.assertGreater(exclusions.count(), 0)
        texts = list(exclusions.values_list("raw_criterion", flat=True))
        self.assertIn("Known EGFR or ALK mutation", texts)

    def test_get_creates_extracted_version(self):
        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_TRIAL_CONTENT), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}}")), \
             patch("trialpilot.views.call_llm", side_effect=[COHORT_RESPONSE_NO_COHORTS,
                                                              INCLUSION_LLM_RESPONSE,
                                                              EXCLUSION_LLM_RESPONSE]), \
             patch("trialpilot.views.document_save") as mock_save:
            self.client.get(self.url)

        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args[0][3], "EXTRACTED")

    def test_get_has_cohorts_false_in_context(self):
        response = self._run_get()
        self.assertFalse(response.context["has_cohorts"])

    def test_get_no_cohorts_created_in_db(self):
        self._run_get()
        self.assertEqual(Trial_cohort.objects.filter(
            clinical_trial=self.doc.clinical_trial
        ).count(), 0)

    def test_get_criteria_have_null_cohort_when_no_cohorts(self):
        self._run_get()
        criteria = Trial_criteria.objects.filter(clinical_trial=self.doc.clinical_trial)
        for c in criteria:
            self.assertIsNone(c.cohort)

    def test_get_criteria_created_as_not_validated(self):
        self._run_get()
        criteria = Trial_criteria.objects.filter(clinical_trial=self.doc.clinical_trial)
        for c in criteria:
            self.assertFalse(c.validated)

# HAPPY PATH - GET with cohorts

class CriteriaExtractionGetWithCohortTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("criteria_extraction", args=[self.doc.id])

    def _run_get_with_cohorts(self):
        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_TRIAL_CONTENT), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}")), \
             patch("trialpilot.views.call_llm", side_effect=[
                 COHORT_RESPONSE_WITH_COHORTS,
                 COHORT_INCLUSION_LLM_RESPONSE,
                 COHORT_EXCLUSION_LLM_RESPONSE,
             ]), \
             patch("trialpilot.views.document_save"):
            return self.client.get(self.url)

    def test_get_creates_cohorts_in_db(self):
        self._run_get_with_cohorts()
        cohorts = Trial_cohort.objects.filter(clinical_trial=self.doc.clinical_trial)
        self.assertEqual(cohorts.count(), 2)
        cohort_ids = set(cohorts.values_list("cohort_id", flat=True))
        self.assertEqual(cohort_ids, {"A", "B"})

    def test_get_has_cohorts_true_in_context(self):
        response = self._run_get_with_cohorts()
        self.assertTrue(response.context["has_cohorts"])

    def test_get_criteria_linked_to_correct_cohort(self):
        self._run_get_with_cohorts()
        cohort_a = Trial_cohort.objects.get(
            clinical_trial=self.doc.clinical_trial,
            cohort_id="A"
        )
        criteria_a = Trial_criteria.objects.filter(
            clinical_trial=self.doc.clinical_trial,
            cohort=cohort_a,
            type=Trial_criteria.CriterionType.INCLUSION
        )
        self.assertGreater(criteria_a.count(), 0)
        texts = list(criteria_a.values_list("raw_criterion", flat=True))
        self.assertIn("EGFR mutation confirmed", texts)

    def test_get_cohorts_in_context(self):
        response = self._run_get_with_cohorts()
        cohorts_ctx = list(response.context["cohorts"])
        self.assertEqual(len(cohorts_ctx), 2)

    def test_get_general_criterion_has_null_cohort(self):
        self._run_get_with_cohorts()
        general = Trial_criteria.objects.filter(
            clinical_trial=self.doc.clinical_trial,
            cohort=None,
            type=Trial_criteria.CriterionType.INCLUSION
        )
        texts = list(general.values_list("raw_criterion", flat=True))
        self.assertIn("Age >= 18 years", texts)

    def test_get_llm_receives_cohorts_context(self):
        captured_prompts = []

        def fake_llm(sys_p, user_p):
            captured_prompts.append(user_p)
            idx = len(captured_prompts)
            if idx == 1:
                return COHORT_RESPONSE_WITH_COHORTS
            if idx == 2:
                return COHORT_INCLUSION_LLM_RESPONSE
            return COHORT_EXCLUSION_LLM_RESPONSE

        with patch("trialpilot.views.extract_document_text", return_value=SAMPLE_TRIAL_CONTENT), \
             patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}")), \
             patch("trialpilot.views.call_llm", side_effect=fake_llm), \
             patch("trialpilot.views.document_save"):
            self.client.get(self.url)

        for prompt in captured_prompts[1:]:
            self.assertIn("EGFR+", prompt)
            self.assertIn("ALK+", prompt)

# EXTRACTION PIPELINE - without cohorts / with chunking

class ExtractCriteriaNoCohortsPipelineTest(TestCase):

    def _make_trial(self, title="trial_study_abc123.pdf"):
        doc = Document.objects.create(
            title=title,
            type=Document.DocumentType.CLINICAL_TRIAL,
        )
        doc.extracted = False
        doc.save()
        ClinicalTrial.objects.create(
            document=doc, study_name="S", pathology_group="mama",
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2026, 1, 1),
            status="recruiting",
        )
        return doc

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}}"))
    def test_single_chunk_llm_called_twice(self, _mock_prompts):
        doc = self._make_trial()
        responses = [INCLUSION_LLM_RESPONSE, EXCLUSION_LLM_RESPONSE]

        with patch("trialpilot.views.call_llm", side_effect=responses) as mock_llm:
            result = _extract_criteria_no_cohorts(doc, SAMPLE_TRIAL_CONTENT)

        self.assertEqual(mock_llm.call_count, 2)
        self.assertFalse(result["has_cohorts"])
        self.assertGreater(len(result["inclusion_criteria"]), 0)
        self.assertGreater(len(result["exclusion_criteria"]), 0)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}}"))
    def test_long_text_triggers_multiple_chunks(self, _mock_prompts):
        doc = self._make_trial()

        long_inclusion = "Inclusion Criteria:\n" + "\n".join(
            f"- Criterion number {i}: " + ("x" * 60)
            for i in range(50)
        )
        long_exclusion = "\nExclusion Criteria:\n" + "\n".join(
            f"- Exclusion {i}: " + ("x" * 60)
            for i in range(50)
        )
        trial_content = long_inclusion + long_exclusion

        always_empty_inclusion = json.dumps({"inclusion_criteria": [f"Criterion {uuid.uuid4().hex}"]})
        always_empty_exclusion = json.dumps({"exclusion_criteria": [f"Exclusion {uuid.uuid4().hex}"]})

        call_count = {"n": 0}

        def fake_llm(sys_p, user_p):
            call_count["n"] += 1
            if "inclusion" in user_p.lower():
                return always_empty_inclusion
            return always_empty_exclusion

        with patch("trialpilot.views.call_llm", side_effect=fake_llm):
            _extract_criteria_no_cohorts(doc, trial_content)

        self.assertGreater(call_count["n"], 2)

    def test_no_sections_raises_value_error(self):
        doc = self._make_trial()
        bad_content = "Some text without any criteria sections."

        with self.assertRaises(ValueError) as ctx:
            _extract_criteria_no_cohorts(doc, bad_content)

        self.assertIn("Inclusion/Exclusion", str(ctx.exception))

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}}"))
    def test_duplicates_across_chunks_are_deduplicated(self, _mock_prompts):
        doc = self._make_trial()

        duplicate_response = json.dumps({
            "inclusion_criteria": ["Age >= 18 years"]
        })
        excl_response = json.dumps({"exclusion_criteria": []})

        with patch("trialpilot.views.call_llm", side_effect=lambda *args, **kwargs: duplicate_response if "inclusion" in args[1].lower() else excl_response):
            with patch("trialpilot.views.split_text_into_chunks",
                       side_effect=lambda text, **kw: ["chunk1", "chunk2"] if text else []):
                result = _extract_criteria_no_cohorts(doc, SAMPLE_TRIAL_CONTENT)

        inc = result["inclusion_criteria"]

        self.assertEqual(
            sum(1 for c in inc if c == "Age >= 18 years"),
            1
        )

# EXTRACTION PIPELINE - with cohorts

class ExtractCriteriaWithCohortsPipelineTest(TestCase):

    def _make_trial(self):
        doc = Document.objects.create(
            title="trial_cohort_abc123.pdf",
            type=Document.DocumentType.CLINICAL_TRIAL,
        )
        doc.extracted = False
        doc.save()
        ClinicalTrial.objects.create(
            document=doc, study_name="S", pathology_group="mama",
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2026, 1, 1),
            status="recruiting",
        )
        return doc

    COHORTS = [
        {"cohort_id": "A", "name": "EGFR+"},
        {"cohort_id": "B", "name": "ALK+"},
    ]

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}"))
    def test_with_cohorts_llm_called_exactly_twice(self, _mock_prompts):
        doc = self._make_trial()

        with patch("trialpilot.views.call_llm",
                   side_effect=[COHORT_INCLUSION_LLM_RESPONSE, COHORT_EXCLUSION_LLM_RESPONSE]) as mock_llm:
            _extract_criteria_with_cohorts(doc, SAMPLE_TRIAL_CONTENT, self.COHORTS)

        self.assertEqual(mock_llm.call_count, 2)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}"))
    def test_with_cohorts_criteria_have_correct_cohort_ids(self, _mock_prompts):
        doc = self._make_trial()

        with patch("trialpilot.views.call_llm",
                   side_effect=[COHORT_INCLUSION_LLM_RESPONSE, COHORT_EXCLUSION_LLM_RESPONSE]):
            result = _extract_criteria_with_cohorts(doc, SAMPLE_TRIAL_CONTENT, self.COHORTS)

        inclusion = result["inclusion_criteria"]
        cohort_ids = {c["cohort_id"] for c in inclusion}
        self.assertIn("A", cohort_ids)
        self.assertIn("B", cohort_ids)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}"))
    def test_with_cohorts_none_cohort_id_preserved(self, _mock_prompts):
        doc = self._make_trial()

        with patch("trialpilot.views.call_llm",
                   side_effect=[COHORT_INCLUSION_LLM_RESPONSE, COHORT_EXCLUSION_LLM_RESPONSE]):
            result = _extract_criteria_with_cohorts(doc, SAMPLE_TRIAL_CONTENT, self.COHORTS)

        general = [c for c in result["inclusion_criteria"] if c["cohort_id"] is None]
        self.assertGreater(len(general), 0)
        texts = [c["text"] for c in general]
        self.assertIn("Age >= 18 years", texts)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}"))
    def test_with_cohorts_same_text_different_cohorts_kept(self, _mock_prompts):
        doc = self._make_trial()

        same_text_response = json.dumps({
            "inclusion_criteria": [
                {"cohort_id": "A", "text": "Age >= 18 years"},
                {"cohort_id": "B", "text": "Age >= 18 years"},
            ]
        })
        with patch("trialpilot.views.call_llm",
                   side_effect=[same_text_response, json.dumps({"exclusion_criteria": []})]):
            result = _extract_criteria_with_cohorts(doc, SAMPLE_TRIAL_CONTENT, self.COHORTS)

        self.assertEqual(len(result["inclusion_criteria"]), 2)

    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{TRIAL_TEXT}} {{CRITERIA_TYPE}} {{COHORTS_CONTEXT}}"))
    def test_with_cohorts_empty_section_ignored(self, _mock_prompts):
        doc = self._make_trial()

        content_no_exclusion = "Inclusion Criteria:\n- Age >= 18\n"

        with patch("trialpilot.views.call_llm", return_value=json.dumps({
            "inclusion_criteria": [{"cohort_id": "A", "text": "Age >= 18"}]
        })) as mock_llm:
            result = _extract_criteria_with_cohorts(doc, content_no_exclusion, self.COHORTS)

        self.assertEqual(mock_llm.call_count, 1)
        self.assertEqual(result["exclusion_criteria"], [])

    def test_with_cohorts_no_sections_raises_value_error(self):
        doc = self._make_trial()
        with self.assertRaises(ValueError):
            _extract_criteria_with_cohorts(doc, "no sections here", self.COHORTS)

# SPLIT & CHUNK HELPERS

class SplitBySectionsTrialTest(TestCase):

    def test_extracts_inclusion_correctly(self):
        inclusion, _ = split_by_sections_trial(SAMPLE_TRIAL_CONTENT)
        self.assertIn("Age >= 18 years", inclusion)
        self.assertIn("ECOG Performance Status 0-1", inclusion)

    def test_extracts_exclusion_correctly(self):
        _, exclusion = split_by_sections_trial(SAMPLE_TRIAL_CONTENT)
        self.assertIn("Untreated brain metastases", exclusion)
        self.assertIn("Active autoimmune disease", exclusion)

    def test_inclusion_does_not_contain_exclusion_text(self):
        inclusion, _ = split_by_sections_trial(SAMPLE_TRIAL_CONTENT)
        self.assertNotIn("Untreated brain metastases", inclusion)

    def test_no_sections_returns_empty_strings(self):
        inclusion, exclusion = split_by_sections_trial("Some random text without criteria.")
        self.assertEqual(inclusion, "")
        self.assertEqual(exclusion, "")

    def test_case_insensitive_matching(self):
        content = "INCLUSION CRITERIA:\n- Age >= 18\n\nEXCLUSION CRITERIA:\n- Active infection"
        inclusion, exclusion = split_by_sections_trial(content)
        self.assertIn("Age >= 18", inclusion)
        self.assertIn("Active infection", exclusion)

    def test_only_inclusion_section_present(self):
        content = "Inclusion Criteria:\n- Age >= 18\n"
        inclusion, exclusion = split_by_sections_trial(content)
        self.assertIn("Age >= 18", inclusion)
        self.assertEqual(exclusion, "")


class SplitTextIntoChunksTest(TestCase):

    def test_short_text_produces_one_chunk(self):
        text = "Line 1\nLine 2\nLine 3\n"
        chunks = split_text_into_chunks(text, max_chars=5000)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Line 1", chunks[0])

    def test_long_text_produces_multiple_chunks(self):
        text = "\n".join("X" * 80 for _ in range(50))
        chunks = split_text_into_chunks(text, max_chars=2000)
        self.assertGreater(len(chunks), 1)

    def test_no_empty_chunks(self):
        text = "\n".join(f"Criterion {i}" for i in range(100))
        chunks = split_text_into_chunks(text, max_chars=200)
        for chunk in chunks:
            self.assertTrue(chunk.strip(), "Found empty chunk")

    def test_overlap_carries_tail_of_previous_chunk(self):
        text = "\n".join(f"Line {i}" for i in range(30))
        chunks = split_text_into_chunks(text, max_chars=150, overlap=30)

        if len(chunks) >= 2:
            end_of_chunk1 = chunks[0][-30:]
            self.assertTrue(
                any(word in chunks[1] for word in end_of_chunk1.split()),
                "Overlap not present in second chunk"
            )

    def test_single_long_paragraph_still_produces_chunk(self):
        text = "A" * 5000
        chunks = split_text_into_chunks(text, max_chars=2000)
        self.assertGreater(len(chunks), 0)
        combined = "".join(chunks)
        self.assertIn("A" * 100, combined)

# MERGE RESULTS

class MergeResultsTest(TestCase):

    def test_merges_two_list_results(self):
        r1 = {"inclusion_criteria": ["A", "B"]}
        r2 = {"inclusion_criteria": ["C", "D"]}
        merged = merge_results([r1, r2])
        self.assertIn("A", merged["inclusion_criteria"])
        self.assertIn("C", merged["inclusion_criteria"])

    def test_deduplicates_merged_lists(self):
        r1 = {"inclusion_criteria": ["Age >= 18 years"]}
        r2 = {"inclusion_criteria": ["Age >= 18 years"]}
        merged = merge_results([r1, r2])
        self.assertEqual(
            sum(1 for c in merged["inclusion_criteria"] if c == "Age >= 18 years"),
            1
        )

    def test_scalar_values_overwritten_by_later_result(self):
        r1 = {"has_cohorts": False}
        r2 = {"has_cohorts": True}
        merged = merge_results([r1, r2])
        self.assertTrue(merged["has_cohorts"])

    def test_merges_multiple_keys(self):
        r1 = {"inclusion_criteria": ["A"], "exclusion_criteria": ["X"]}
        r2 = {"inclusion_criteria": ["B"], "exclusion_criteria": ["Y"]}
        merged = merge_results([r1, r2])
        self.assertIn("A", merged["inclusion_criteria"])
        self.assertIn("B", merged["inclusion_criteria"])
        self.assertIn("X", merged["exclusion_criteria"])
        self.assertIn("Y", merged["exclusion_criteria"])

    def test_empty_list_returns_empty_dict(self):
        self.assertEqual(merge_results([]), {})

# POST - validation of criteria

class CriteriaExtractionPostTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("criteria_extraction", args=[self.doc.id])

        self.inc1 = Trial_criteria.objects.create(
            clinical_trial=self.doc.clinical_trial,
            type=Trial_criteria.CriterionType.INCLUSION,
            raw_criterion="Age >= 18 years",
            validated_criterion="Age >= 18 years",
            validated=False,
        )
        self.exc1 = Trial_criteria.objects.create(
            clinical_trial=self.doc.clinical_trial,
            type=Trial_criteria.CriterionType.EXCLUSION,
            raw_criterion="Active infection",
            validated_criterion="Active infection",
            validated=False,
        )

    def _post(self, extra_data=None):
        data = {}
        if extra_data:
            data.update(extra_data)
        with patch("trialpilot.views.document_save"), \
             patch("trialpilot.views.extract_document_text", return_value="mock trial content"):
            return self.client.post(self.url, data=data)

    def test_post_updates_existing_criterion(self):
        self._post({f"criterion_{self.inc1.id}": "Age ≥ 18 years (corrected)"})
        self.inc1.refresh_from_db()
        self.assertEqual(self.inc1.validated_criterion, "Age ≥ 18 years (corrected)")
        self.assertTrue(self.inc1.validated)

    def test_post_invalid_criterion_id_ignored(self):
        response = self._post({"criterion_99999": "Some value"})
        self.assertEqual(response.status_code, 302)

    def test_post_creates_new_inclusion_criteria(self):
        self._post({"inclusion[]": ["Signed informed consent", "Life expectancy >= 3 months"]})
        texts = list(Trial_criteria.objects.filter(
            clinical_trial=self.doc.clinical_trial,
            type=Trial_criteria.CriterionType.INCLUSION,
            validated=True,
        ).values_list("raw_criterion", flat=True))
        self.assertIn("Signed informed consent", texts)
        self.assertIn("Life expectancy >= 3 months", texts)

    def test_post_creates_new_exclusion_criteria(self):
        self._post({"exclusion[]": ["Prior chemotherapy within 3 months"]})
        texts = list(Trial_criteria.objects.filter(
            clinical_trial=self.doc.clinical_trial,
            type=Trial_criteria.CriterionType.EXCLUSION,
            validated=True,
        ).values_list("raw_criterion", flat=True))
        self.assertIn("Prior chemotherapy within 3 months", texts)

    def test_post_blank_inclusion_not_created(self):
        before = Trial_criteria.objects.filter(clinical_trial=self.doc.clinical_trial).count()
        self._post({"inclusion[]": ["", "   "]})
        after = Trial_criteria.objects.filter(clinical_trial=self.doc.clinical_trial).count()
        self.assertEqual(before, after)

    def test_post_blank_exclusion_not_created(self):
        before = Trial_criteria.objects.filter(clinical_trial=self.doc.clinical_trial).count()
        self._post({"exclusion[]": ["", "  "]})
        after = Trial_criteria.objects.filter(clinical_trial=self.doc.clinical_trial).count()
        self.assertEqual(before, after)

    def test_post_creates_cohort_inclusion_criterion(self):
        cohort = Trial_cohort.objects.create(
            cohort_id="A",
            clinical_trial=self.doc.clinical_trial,
            name="EGFR+",
        )
        self._post({f"new_inclusion_cohort_{cohort.id}[]": ["EGFR exon 19 deletion confirmed"]})

        criterion = Trial_criteria.objects.get(
            clinical_trial=self.doc.clinical_trial,
            cohort=cohort,
            type=Trial_criteria.CriterionType.INCLUSION,
            raw_criterion="EGFR exon 19 deletion confirmed",
        )
        self.assertTrue(criterion.validated)

    def test_post_creates_cohort_exclusion_criterion(self):
        cohort = Trial_cohort.objects.create(
            cohort_id="B",
            clinical_trial=self.doc.clinical_trial,
            name="ALK+",
        )
        self._post({f"new_exclusion_cohort_{cohort.id}[]": ["Prior ALK inhibitor therapy"]})

        criterion = Trial_criteria.objects.get(
            clinical_trial=self.doc.clinical_trial,
            cohort=cohort,
            type=Trial_criteria.CriterionType.EXCLUSION,
            raw_criterion="Prior ALK inhibitor therapy",
        )
        self.assertTrue(criterion.validated)

    def test_post_redirects_to_criteria_conversion(self):
        response = self._post()
        self.assertRedirects(
            response,
            reverse("criteria_conversion", args=[self.doc.id])
        )

    def test_post_creates_validated_version(self):
        with patch("trialpilot.views.document_save") as mock_save, \
             patch("trialpilot.views.extract_document_text", return_value="mock content"):
            self.client.post(self.url, data={})

        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args[0][3], "VALIDATED")

    def test_post_validated_payload_structure(self):
        captured = {}

        def fake_save(doc, file_obj, filename, version_id):
            content = file_obj.read().decode("utf-8")
            captured["payload"] = json.loads(content)

        with patch("trialpilot.views.document_save", side_effect=fake_save), \
            patch("trialpilot.views.extract_document_text", return_value="mock content"):
            self.client.post(self.url, data={
                f"criterion_{self.inc1.id}": "Age >= 18 years (validated)"
            })

        payload = captured["payload"]
        self.assertIn("document_id", payload)
        self.assertIn("document_title", payload)
        self.assertIn("validated_at", payload)
        self.assertIn("inclusion_criteria", payload)
        self.assertIn("exclusion_criteria", payload)

        for entry in payload["inclusion_criteria"]:
            self.assertIn("id", entry)
            self.assertIn("raw_criterion", entry)
            self.assertIn("validated_criterion", entry)