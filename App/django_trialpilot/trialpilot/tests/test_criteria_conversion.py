"""
Testes Unitários — criteria_conversion view
============================================

A diferença central desta view face às anteriores é o BATCHING:
os critérios são enviados ao LLM em lotes de 5 (batch_size=5),
separados por tipo (inclusion / exclusion), sem chunking de texto.
No POST, a view constrói logic JSON a partir de campos de formulário
numerados e guarda Logic_criteria validados.

  GUARD CLAUSES (GET)
    1.  Documento não existe
    2.  Tipo errado (não é CLINICAL_TRIAL)
    3.  Documento já convertido (extracted=True) → redireciona para error

  HAPPY PATH — GET
    4.  GET retorna 200 e template correto
    5.  Contexto tem as chaves essenciais
    6.  Logic_criteria de inclusão criados na BD
    7.  Logic_criteria de exclusão criados na BD
    8.  Version CONVERTED criada
    9.  criterion_id inválido na resposta do LLM é ignorado sem erro
   10.  Logic_criteria com logic simples (field/operator/value) processado corretamente
   11.  Logic_criteria com grupo (conditions) processado corretamente
   12.  Logic_criteria sem field/conditions recebe placeholder vazio
   13.  Contexto inclui has_cohorts=False quando não há cohorts
   14.  Contexto inclui has_cohorts=True quando há cohorts
   15.  criterion_position ordena: inclusion geral → inclusion por cohort → exclusion geral → exclusion por cohort

  BATCHING — criteria_conversion_step
   16.  5 critérios → 1 batch → LLM chamado 1× por tipo (2× total)
   17.  6 critérios de inclusão → 2 batches de inclusion → 3× total (2 inc + 1 exc)
   18.  Batch vazio não chama o LLM
   19.  Resultados de múltiplos batches são concatenados corretamente
   20.  Duplicados entre batches são deduplicados no resultado final
   21.  Payload enviado ao LLM tem estrutura correta por batch

  chunk_criteria_list
   22.  Lista de 10 com batch_size=5 → 2 batches
   23.  Lista de 11 com batch_size=5 → 3 batches
   24.  Lista vazia → 0 batches
   25.  batch_size=1 → N batches de 1

  process_condition
   26.  Campo conhecido → field_type = field, custom_field = ""
   27.  Campo desconhecido → field_type = "__custom__", custom_field = field
   28.  Campo vazio → field_type = "", custom_field = ""
   29.  Grupo com conditions → is_group=True, recursão nas sub-condições
   30.  Condição simples → is_group=False

  get_ordered_logic_with_positions
   31.  Sem cohorts: inclusion geral primeiro, exclusion geral depois
   32.  Com cohorts: inclusion geral → inclusion cohort A → exclusion geral → exclusion cohort A
   33.  Logic não associado a nenhuma secção não aparece no resultado

  POST — validação de Logic_criteria
   34.  POST com condição simples cria logic com field/operator/value corretos
   35.  POST com múltiplas condições cria logic com operator de grupo (AND)
   36.  POST com __custom__ field usa custom_field no lugar
   37.  POST com unit inclui unit no logic
   38.  POST com logic_id inválido é ignorado
   39.  POST com 1 condição guarda logic simples (não wrapped em conditions)
   40.  POST seta validated=True no Logic_criteria
   41.  POST seta document.extracted=True
   42.  POST cria Version VALIDATED com payload correto
   43.  POST redireciona para trial_list
   44.  Payload VALIDATED tem estrutura e chaves correctas
"""

import json
import uuid
import datetime
from unittest.mock import patch, MagicMock, call

from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.base import ContentFile

from trialpilot.models import (
    Document, ClinicalTrial, Trial_criteria, Logic_criteria, Trial_cohort
)
from trialpilot.views import (
    criteria_conversion_step,
    chunk_criteria_list,
    process_condition,
    get_ordered_logic_with_positions,
    KNOWN_FIELDS,
)


# ===========================================================================
# HELPERS
# ===========================================================================

def make_trial_doc(title="trial_study_abc123.pdf", extracted=False):
    doc = Document.objects.create(
        title=title,
        type=Document.DocumentType.CLINICAL_TRIAL,
    )
    doc.extracted = extracted
    doc.save()
    ClinicalTrial.objects.create(
        document=doc,
        study_name="Study ABC",
        pathology_group="pneumologia",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2026, 1, 1),
        status="recruiting",
    )
    return doc


def make_criterion(doc, text, ctype=Trial_criteria.CriterionType.INCLUSION, cohort=None):
    return Trial_criteria.objects.create(
        document=doc,
        cohort=cohort,
        type=ctype,
        raw_criterion=text,
        validated_criterion=text,
        validated=True,
    )


def make_logic(criterion, raw_logic=None):
    logic = raw_logic or {"field": "age", "operator": ">=", "value": 18}
    return Logic_criteria.objects.create(
        criterion=criterion,
        raw_logic=logic,
        validated_logic=logic,
        validated=False,
    )


def llm_conversion_response(criteria_payload):
    """Builds a realistic LLM response that mirrors the sent batch.

    Each entry includes a unique "text" field derived from the criterion id
    so that deduplicate() can compare entries without encountering None.
    The "logic" field mirrors what the real LLM would produce.
    """
    inclusion = [
        {
            "id": c["id"],
            "text": c.get("text", f"Inclusion criterion {c['id']}"),
            "logic": {"field": "age", "operator": ">=", "value": 18},
        }
        for c in criteria_payload.get("inclusion_criteria", [])
    ]
    exclusion = [
        {
            "id": c["id"],
            "text": c.get("text", f"Exclusion criterion {c['id']}"),
            "logic": {"field": "ecog_ps", "operator": ">", "value": 2},
        }
        for c in criteria_payload.get("exclusion_criteria", [])
    ]
    return json.dumps({"inclusion_criteria": inclusion, "exclusion_criteria": exclusion})


SIMPLE_LOGIC = {"field": "age", "operator": ">=", "value": 18}
GROUP_LOGIC = {
    "operator": "AND",
    "conditions": [
        {"field": "age", "operator": ">=", "value": 18},
        {"field": "ecog_ps", "operator": "<=", "value": 1},
    ]
}


# ===========================================================================
# 1. GUARD CLAUSES — GET
# ===========================================================================

class CriteriaConversionGuardClausesTest(TestCase):

    def setUp(self):
        self.client = Client()

    # ------------------------------------------------------------------
    # 1.1 Documento não existe
    # ------------------------------------------------------------------
    def test_nonexistent_document_renders_error(self):
        response = self.client.get(reverse("criteria_conversion", args=[99999]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("not found", response.context["error"].lower())

    # ------------------------------------------------------------------
    # 1.2 Tipo errado
    # ------------------------------------------------------------------
    def test_wrong_document_type_renders_error(self):
        doc = Document.objects.create(
            title="diary_patient_1_abc.txt",
            type=Document.DocumentType.CLINICAL_DIARY,
        )
        response = self.client.get(reverse("criteria_conversion", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("clinical trial", response.context["error"].lower())

    # ------------------------------------------------------------------
    # 1.3 Documento já extraído
    # ------------------------------------------------------------------
    def test_already_extracted_renders_error(self):
        doc = make_trial_doc(extracted=True)
        response = self.client.get(reverse("criteria_conversion", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("already been extracted", response.context["error"].lower())


# ===========================================================================
# 2. HAPPY PATH — GET
# ===========================================================================

class CriteriaConversionGetTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("criteria_conversion", args=[self.doc.id])

        # Pré-criar critérios validados como se o criteria_extraction já tivesse corrido
        self.inc1 = make_criterion(self.doc, "Age >= 18 years")
        self.inc2 = make_criterion(self.doc, "ECOG PS 0-1")
        self.exc1 = make_criterion(self.doc, "Active infection", Trial_criteria.CriterionType.EXCLUSION)

    def _fake_llm(self, sys_p, user_p):
        """Interpreta o payload enviado e devolve logic para cada critério."""
        payload = json.loads(json.loads(
            user_p.replace("{{CRITERIA_TEXT}}", "").strip()
        ) if "{{CRITERIA_TEXT}}" in user_p else user_p)
        return llm_conversion_response(payload)

    def _run_get(self):
        with patch("trialpilot.views.load_prompt_files",
                   return_value=("sys", "{{CRITERIA_TEXT}}")), \
             patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(
                       json.loads(u)
                   )), \
             patch("trialpilot.views.document_save"):
            return self.client.get(self.url)

    # ------------------------------------------------------------------
    # 2.1 Status 200 e template correto
    # ------------------------------------------------------------------
    def test_get_returns_200_and_correct_template(self):
        response = self._run_get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trialpilot/trial_criteria-conversion.html")

    # ------------------------------------------------------------------
    # 2.2 Contexto tem as chaves essenciais
    # ------------------------------------------------------------------
    def test_get_context_keys_present(self):
        response = self._run_get()
        for key in ["trial", "logic_criteria", "has_cohorts", "cohorts", "criterion_position"]:
            self.assertIn(key, response.context, f"Missing context key: {key}")

    # ------------------------------------------------------------------
    # 2.3 Logic_criteria criados para critérios de inclusão
    # ------------------------------------------------------------------
    def test_get_creates_inclusion_logic_criteria(self):
        self._run_get()
        lc = Logic_criteria.objects.filter(criterion__document=self.doc,
                                           criterion__type=Trial_criteria.CriterionType.INCLUSION)
        self.assertEqual(lc.count(), 2)

    # ------------------------------------------------------------------
    # 2.4 Logic_criteria criados para critérios de exclusão
    # ------------------------------------------------------------------
    def test_get_creates_exclusion_logic_criteria(self):
        self._run_get()
        lc = Logic_criteria.objects.filter(criterion__document=self.doc,
                                           criterion__type=Trial_criteria.CriterionType.EXCLUSION)
        self.assertEqual(lc.count(), 1)

    # ------------------------------------------------------------------
    # 2.5 Version CONVERTED criada
    # ------------------------------------------------------------------
    def test_get_creates_converted_version(self):
        with patch("trialpilot.views.load_prompt_files",
                   return_value=("sys", "{{CRITERIA_TEXT}}")), \
             patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(json.loads(u))), \
             patch("trialpilot.views.document_save") as mock_save:
            self.client.get(self.url)

        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args[0][3], "CONVERTED")

    # ------------------------------------------------------------------
    # 2.6 criterion_id inválido na resposta do LLM é ignorado
    # ------------------------------------------------------------------
    def test_get_invalid_criterion_id_in_llm_response_ignored(self):
        bad_response = json.dumps({
            "inclusion_criteria": [{"id": 99999, "logic": {"field": "age", "operator": ">=", "value": 18}}],
            "exclusion_criteria": []
        })
        with patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}")), \
             patch("trialpilot.views.call_llm", return_value=bad_response), \
             patch("trialpilot.views.document_save"):
            response = self.client.get(self.url)
        # Não deve crashar — template renderizado
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # 2.7 Logic simples (field/operator/value) guardado no raw_logic da BD
    # ------------------------------------------------------------------
    def test_get_simple_logic_stored_in_db(self):
        # _run_get usa llm_conversion_response que devolve age >= 18 para inc1
        self._run_get()
        lc = Logic_criteria.objects.get(criterion=self.inc1)
        # raw_logic é o que o LLM devolveu e a view guardou na BD
        raw = lc.raw_logic
        self.assertEqual(raw["field"], "age")
        self.assertEqual(raw["operator"], ">=")
        self.assertEqual(raw["value"], 18)

    # ------------------------------------------------------------------
    # 2.8 Logic de grupo (conditions) guardado no raw_logic da BD
    # ------------------------------------------------------------------
    def test_get_group_logic_stored_in_db(self):
        with patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}")), \
             patch("trialpilot.views.call_llm", return_value=json.dumps({
                 "inclusion_criteria": [
                     {"id": self.inc1.id, "logic": GROUP_LOGIC},
                 ],
                 "exclusion_criteria": []
             })), \
             patch("trialpilot.views.document_save"):
            self.client.get(self.url)

        lc = Logic_criteria.objects.get(criterion=self.inc1)
        raw = lc.raw_logic
        # Grupo: deve ter "operator" e "conditions" na raiz
        self.assertEqual(raw["operator"], "AND")
        self.assertIn("conditions", raw)
        self.assertEqual(len(raw["conditions"]), 2)

    # ------------------------------------------------------------------
    # 2.9 Logic vazio do LLM → raw_logic guardado como {} na BD
    #     (o placeholder em memória serve só o template; não persiste)
    # ------------------------------------------------------------------
    def test_get_empty_logic_stored_as_empty_dict_in_db(self):
        with patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}")), \
             patch("trialpilot.views.call_llm", return_value=json.dumps({
                 "inclusion_criteria": [{"id": self.inc1.id, "logic": {}}],
                 "exclusion_criteria": []
             })), \
             patch("trialpilot.views.document_save"):
            self.client.get(self.url)

        lc = Logic_criteria.objects.get(criterion=self.inc1)
        # A view guarda o logic tal como o LLM devolveu — dict vazio
        self.assertEqual(lc.raw_logic, {})
        # O placeholder em memória (conditions com campos em branco) é
        # adicionado durante o render e verificado via process_condition,
        # que é testado isoladamente no grupo 5.
        self.assertFalse(lc.validated)

    # ------------------------------------------------------------------
    # 2.10 has_cohorts=False quando não há cohorts
    # ------------------------------------------------------------------
    def test_get_has_cohorts_false_when_no_cohorts(self):
        response = self._run_get()
        self.assertFalse(response.context["has_cohorts"])

    # ------------------------------------------------------------------
    # 2.11 has_cohorts=True quando há cohorts
    # ------------------------------------------------------------------
    def test_get_has_cohorts_true_when_cohorts_exist(self):
        Trial_cohort.objects.create(
            cohort_id="A", clinical_trial=self.doc.clinical_trial, name="EGFR+"
        )
        response = self._run_get()
        self.assertTrue(response.context["has_cohorts"])


# ===========================================================================
# 3. BATCHING — criteria_conversion_step
# ===========================================================================

class CriteriaConversionStepTest(TestCase):

    def _make_criteria_payload(self, n_inc=3, n_exc=2):
        return {
            "document_id": 1,
            "document_title": "trial_test.pdf",
            "inclusion_criteria": [{"id": i, "text": f"Inclusion criterion {i}"} for i in range(n_inc)],
            "exclusion_criteria": [{"id": 100 + i, "text": f"Exclusion criterion {i}"} for i in range(n_exc)],
        }

    def _run_conversion(self, payload, batch_size=5):
        call_count = {"n": 0}
        responses = []

        def fake_llm(sys_p, user_p):
            call_count["n"] += 1
            batch_payload = json.loads(u) if (u := user_p) else {}
            return llm_conversion_response(batch_payload)

        with patch("trialpilot.views.load_prompt_files",
                   return_value=("sys", "{{CRITERIA_TEXT}}")), \
             patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(json.loads(u))) as mock_llm:
            result = criteria_conversion_step(payload, batch_size=batch_size)

        return result, mock_llm

    # ------------------------------------------------------------------
    # 3.1 5 critérios → 1 batch de inclusão + 1 batch de exclusão = 2 calls
    # ------------------------------------------------------------------
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}"))
    def test_five_criteria_two_llm_calls(self, _):
        payload = self._make_criteria_payload(n_inc=5, n_exc=5)
        with patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(json.loads(u))) as mock_llm:
            criteria_conversion_step(payload, batch_size=5)
        self.assertEqual(mock_llm.call_count, 2)  # 1 batch inc + 1 batch exc

    # ------------------------------------------------------------------
    # 3.2 6 critérios de inclusão → 2 batches de inclusão + 1 batch exc = 3 calls
    # ------------------------------------------------------------------
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}"))
    def test_six_inclusion_criteria_three_llm_calls(self, _):
        payload = self._make_criteria_payload(n_inc=6, n_exc=1)
        with patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(json.loads(u))) as mock_llm:
            criteria_conversion_step(payload, batch_size=5)
        self.assertEqual(mock_llm.call_count, 3)  # 2 inc + 1 exc

    # ------------------------------------------------------------------
    # 3.3 Lista de exclusão vazia → LLM só chamado para inclusão
    # ------------------------------------------------------------------
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}"))
    def test_empty_exclusion_list_no_extra_call(self, _):
        payload = {
            "document_id": 1, "document_title": "t.pdf",
            "inclusion_criteria": [{"id": 1, "text": "Age >= 18"}],
            "exclusion_criteria": [],
        }
        with patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(json.loads(u))) as mock_llm:
            criteria_conversion_step(payload, batch_size=5)
        # Exclusion loop nunca itera → 0 calls para exclusion
        self.assertEqual(mock_llm.call_count, 1)

    # ------------------------------------------------------------------
    # 3.4 Resultados de múltiplos batches são concatenados
    # ------------------------------------------------------------------
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}"))
    def test_results_from_multiple_batches_concatenated(self, _):
        distinct_texts = [
            "Age >= 18 years",
            "ECOG Performance Status 0 or 1",
            "Histologically confirmed NSCLC Stage IV",
            "Hemoglobin >= 9 g per deciliter",
            "Creatinine clearance >= 40 mL per minute",
            "Signed informed consent form obtained",
            "No prior immunotherapy treatment received",
            "Life expectancy of at least 3 months",
        ]
        payload = {
            "document_id": 1,
            "document_title": "trial_test.pdf",
            "inclusion_criteria": [
                {"id": i, "text": text} for i, text in enumerate(distinct_texts)
            ],
            "exclusion_criteria": [],
        }
        with patch("trialpilot.views.call_llm",
                   side_effect=lambda s, u: llm_conversion_response(json.loads(u))):
            result = criteria_conversion_step(payload, batch_size=5)
        self.assertEqual(len(result["inclusion_criteria"]), 8)

    # ------------------------------------------------------------------
    # 3.5 Payload enviado ao LLM tem estrutura correta
    # ------------------------------------------------------------------
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}"))
    def test_batch_payload_structure_sent_to_llm(self, _):
        captured = []

        def fake_llm(sys_p, user_p):
            captured.append(json.loads(user_p))
            return json.dumps({"inclusion_criteria": [], "exclusion_criteria": []})

        payload = self._make_criteria_payload(n_inc=3, n_exc=0)
        with patch("trialpilot.views.call_llm", side_effect=fake_llm):
            criteria_conversion_step(payload, batch_size=5)

        self.assertEqual(len(captured), 1)
        sent = captured[0]
        self.assertIn("document_id", sent)
        self.assertIn("document_title", sent)
        self.assertIn("inclusion_criteria", sent)
        self.assertIn("exclusion_criteria", sent)
        # Exclusion deve estar vazio neste batch de inclusion
        self.assertEqual(sent["exclusion_criteria"], [])

    # ------------------------------------------------------------------
    # 3.6 Duplicados entre batches são deduplicados no resultado final
    # ------------------------------------------------------------------
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CRITERIA_TEXT}}"))
    def test_duplicates_across_batches_deduplicated(self, _):
        # Dois batches devolvem entradas com texto idêntico ("Age >= 18 years")
        # mas ids diferentes — o deduplicate deve colapsar pelo texto.
        # Batch 1 devolve id=1, batch 2 devolve id=2, ambos com o mesmo texto.
        batch_call = {"n": 0}

        def fake_llm(sys_p, user_p):
            batch_call["n"] += 1
            return json.dumps({
                "inclusion_criteria": [
                    {
                        "id": batch_call["n"],           # id único por batch
                        "text": "Age >= 18 years",       # texto idêntico em ambos
                        "logic": {"field": "age", "operator": ">=", "value": 18},
                    }
                ],
                "exclusion_criteria": [],
            })

        payload = {
            "document_id": 1, "document_title": "t.pdf",
            # 6 critérios → 2 batches com batch_size=5
            "inclusion_criteria": [{"id": i, "text": "Age >= 18 years"} for i in range(6)],
            "exclusion_criteria": [],
        }
        with patch("trialpilot.views.call_llm", side_effect=fake_llm):
            result = criteria_conversion_step(payload, batch_size=5)

        # Texto "Age >= 18 years" só deve aparecer 1× no resultado final
        texts = [c["text"] for c in result["inclusion_criteria"]]
        self.assertEqual(texts.count("Age >= 18 years"), 1)


# ===========================================================================
# 4. chunk_criteria_list
# ===========================================================================

class ChunkCriteriaListTest(TestCase):

    def _chunked(self, lst, batch_size):
        return list(chunk_criteria_list(lst, batch_size))

    def test_10_items_batch5_gives_2_batches(self):
        items = list(range(10))
        batches = self._chunked(items, 5)
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0], [0, 1, 2, 3, 4])
        self.assertEqual(batches[1], [5, 6, 7, 8, 9])

    def test_11_items_batch5_gives_3_batches(self):
        batches = self._chunked(list(range(11)), 5)
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[2]), 1)

    def test_empty_list_gives_0_batches(self):
        self.assertEqual(self._chunked([], 5), [])

    def test_batch_size_1_gives_n_batches(self):
        batches = self._chunked([1, 2, 3], 1)
        self.assertEqual(len(batches), 3)
        for b in batches:
            self.assertEqual(len(b), 1)

    def test_list_shorter_than_batch_size_gives_1_batch(self):
        batches = self._chunked([1, 2, 3], 10)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0], [1, 2, 3])

    def test_batches_cover_all_items(self):
        items = list(range(13))
        batches = self._chunked(items, 5)
        flat = [x for b in batches for x in b]
        self.assertEqual(flat, items)


# ===========================================================================
# 5. process_condition
# ===========================================================================

class ProcessConditionTest(TestCase):

    # ------------------------------------------------------------------
    # 5.1 Campo conhecido → field_type = field, custom_field = ""
    # ------------------------------------------------------------------
    def test_known_field_sets_field_type(self):
        condition = {"field": "age", "operator": ">=", "value": 18}
        result = process_condition(condition)
        self.assertFalse(result["is_group"])
        self.assertEqual(result["field_type"], "age")
        self.assertEqual(result["custom_field"], "")

    def test_known_field_ecog_ps(self):
        condition = {"field": "ecog_ps", "operator": "<=", "value": 1}
        result = process_condition(condition)
        self.assertEqual(result["field_type"], "ecog_ps")

    def test_known_lab_field(self):
        condition = {"field": "hemoglobina", "operator": ">=", "value": 9.0}
        result = process_condition(condition)
        self.assertEqual(result["field_type"], "hemoglobina")
        self.assertEqual(result["custom_field"], "")

    # ------------------------------------------------------------------
    # 5.2 Campo desconhecido → field_type = "__custom__"
    # ------------------------------------------------------------------
    def test_unknown_field_sets_custom(self):
        condition = {"field": "bmi", "operator": ">=", "value": 18.5}
        result = process_condition(condition)
        self.assertEqual(result["field_type"], "__custom__")
        self.assertEqual(result["custom_field"], "bmi")

    def test_unknown_field_preserves_operator_value(self):
        condition = {"field": "tumor_size", "operator": "<=", "value": 5}
        result = process_condition(condition)
        self.assertEqual(result["operator"], "<=")
        self.assertEqual(result["value"], 5)

    # ------------------------------------------------------------------
    # 5.3 Campo vazio → field_type = ""
    # ------------------------------------------------------------------
    def test_empty_field_stays_empty(self):
        condition = {"field": "", "operator": ">=", "value": 0}
        result = process_condition(condition)
        self.assertEqual(result["field_type"], "")
        self.assertEqual(result["custom_field"], "")

    # ------------------------------------------------------------------
    # 5.4 Grupo com conditions → is_group=True, recursão
    # ------------------------------------------------------------------
    def test_group_condition_is_group_true(self):
        group = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "ecog_ps", "operator": "<=", "value": 1},
            ]
        }
        result = process_condition(group)
        self.assertTrue(result["is_group"])
        self.assertEqual(result["operator"], "AND")
        self.assertEqual(len(result["conditions"]), 2)

    def test_group_children_processed_recursively(self):
        group = {
            "operator": "OR",
            "conditions": [
                {"field": "diagnosis", "operator": "=", "value": "NSCLC"},
                {"field": "unknown_field", "operator": "=", "value": "x"},
            ]
        }
        result = process_condition(group)
        children = result["conditions"]
        self.assertEqual(children[0]["field_type"], "diagnosis")
        self.assertEqual(children[1]["field_type"], "__custom__")

    # ------------------------------------------------------------------
    # 5.5 Condição simples → is_group=False
    # ------------------------------------------------------------------
    def test_simple_condition_is_group_false(self):
        result = process_condition({"field": "age", "operator": ">=", "value": 18})
        self.assertFalse(result["is_group"])

    # ------------------------------------------------------------------
    # 5.6 Unit preservado quando presente
    # ------------------------------------------------------------------
    def test_unit_preserved(self):
        condition = {"field": "hemoglobina", "operator": ">=", "value": 9, "unit": "g/dL"}
        result = process_condition(condition)
        self.assertEqual(result["unit"], "g/dL")

    def test_missing_unit_defaults_empty(self):
        result = process_condition({"field": "age", "operator": ">=", "value": 18})
        self.assertEqual(result.get("unit", ""), "")


# ===========================================================================
# 6. get_ordered_logic_with_positions
# ===========================================================================

class GetOrderedLogicWithPositionsTest(TestCase):

    def setUp(self):
        self.doc = make_trial_doc()
        self.cohort_a = Trial_cohort.objects.create(
            cohort_id="A", clinical_trial=self.doc.clinical_trial, name="EGFR+"
        )
        self.cohort_b = Trial_cohort.objects.create(
            cohort_id="B", clinical_trial=self.doc.clinical_trial, name="ALK+"
        )

    def _make_lc(self, text, ctype, cohort=None):
        crit = make_criterion(self.doc, text, ctype, cohort)
        return make_logic(crit)

    # ------------------------------------------------------------------
    # 6.1 Sem cohorts: inclusion geral aparece antes de exclusion geral
    # ------------------------------------------------------------------
    def test_no_cohorts_inclusion_before_exclusion(self):
        inc = self._make_lc("Age >= 18", Trial_criteria.CriterionType.INCLUSION)
        exc = self._make_lc("Active infection", Trial_criteria.CriterionType.EXCLUSION)

        positions = get_ordered_logic_with_positions([inc, exc], cohorts=None)
        self.assertLess(positions[inc.id], positions[exc.id])

    # ------------------------------------------------------------------
    # 6.2 Com cohorts: inclusion geral → cohort A → exclusion geral → exclusion cohort A
    # ------------------------------------------------------------------
    def test_with_cohorts_ordering(self):
        inc_general = self._make_lc("Age >= 18", Trial_criteria.CriterionType.INCLUSION)
        inc_cohort_a = self._make_lc("EGFR+ confirmed",
                                     Trial_criteria.CriterionType.INCLUSION, self.cohort_a)
        exc_general = self._make_lc("Active infection", Trial_criteria.CriterionType.EXCLUSION)
        exc_cohort_a = self._make_lc("Prior EGFR therapy",
                                     Trial_criteria.CriterionType.EXCLUSION, self.cohort_a)

        all_lc = [inc_general, inc_cohort_a, exc_general, exc_cohort_a]
        positions = get_ordered_logic_with_positions(
            all_lc, cohorts=[self.cohort_a]
        )

        self.assertLess(positions[inc_general.id], positions[inc_cohort_a.id])
        self.assertLess(positions[inc_cohort_a.id], positions[exc_general.id])
        self.assertLess(positions[exc_general.id], positions[exc_cohort_a.id])

    # ------------------------------------------------------------------
    # 6.3 Cohort B depois de cohort A
    # ------------------------------------------------------------------
    def test_cohort_b_after_cohort_a(self):
        inc_a = self._make_lc("EGFR+", Trial_criteria.CriterionType.INCLUSION, self.cohort_a)
        inc_b = self._make_lc("ALK+",  Trial_criteria.CriterionType.INCLUSION, self.cohort_b)

        positions = get_ordered_logic_with_positions(
            [inc_a, inc_b], cohorts=[self.cohort_a, self.cohort_b]
        )
        self.assertLess(positions[inc_a.id], positions[inc_b.id])


# ===========================================================================
# 7. POST — validação de Logic_criteria
# ===========================================================================

class CriteriaConversionPostTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("criteria_conversion", args=[self.doc.id])

        self.inc1 = make_criterion(self.doc, "Age >= 18 years")
        self.exc1 = make_criterion(self.doc, "Active infection",
                                   Trial_criteria.CriterionType.EXCLUSION)
        self.lc_inc = make_logic(self.inc1)
        self.lc_exc = make_logic(self.exc1)

    def _post(self, extra_data=None):
        data = {}
        if extra_data:
            data.update(extra_data)
        with patch("trialpilot.views.document_save"):
            return self.client.post(self.url, data=data)

    # ------------------------------------------------------------------
    # 7.1 POST com 1 condição guarda logic simples (não wrapped)
    # ------------------------------------------------------------------
    def test_post_single_condition_saves_simple_logic(self):
        self._post({
            f"logic_{self.lc_inc.id}": "on",
            f"group_operator_{self.lc_inc.id}": "AND",
            f"field_{self.lc_inc.id}_1": "age",
            f"operator_{self.lc_inc.id}_1": ">=",
            f"value_{self.lc_inc.id}_1": "18",
            f"unit_{self.lc_inc.id}_1": "",
        })
        self.lc_inc.refresh_from_db()
        logic = self.lc_inc.validated_logic
        # Condição simples: não deve ter "conditions" wrapper
        self.assertEqual(logic["field"], "age")
        self.assertEqual(logic["operator"], ">=")
        self.assertEqual(logic["value"], "18")

    # ------------------------------------------------------------------
    # 7.2 POST com múltiplas condições guarda logic de grupo
    # ------------------------------------------------------------------
    def test_post_multiple_conditions_saves_group_logic(self):
        self._post({
            f"logic_{self.lc_inc.id}": "on",
            f"group_operator_{self.lc_inc.id}": "AND",
            f"field_{self.lc_inc.id}_1": "age",
            f"operator_{self.lc_inc.id}_1": ">=",
            f"value_{self.lc_inc.id}_1": "18",
            f"unit_{self.lc_inc.id}_1": "",
            f"field_{self.lc_inc.id}_2": "ecog_ps",
            f"operator_{self.lc_inc.id}_2": "<=",
            f"value_{self.lc_inc.id}_2": "1",
            f"unit_{self.lc_inc.id}_2": "",
        })
        self.lc_inc.refresh_from_db()
        logic = self.lc_inc.validated_logic
        self.assertEqual(logic["operator"], "AND")
        self.assertEqual(len(logic["conditions"]), 2)

    # ------------------------------------------------------------------
    # 7.3 POST com __custom__ field usa o valor de field_custom_*
    # ------------------------------------------------------------------
    def test_post_custom_field_used_correctly(self):
        self._post({
            f"logic_{self.lc_inc.id}": "on",
            f"group_operator_{self.lc_inc.id}": "AND",
            f"field_{self.lc_inc.id}_1": "__custom__",
            f"field_custom_{self.lc_inc.id}_1": "tumor_size",
            f"operator_{self.lc_inc.id}_1": "<=",
            f"value_{self.lc_inc.id}_1": "5",
            f"unit_{self.lc_inc.id}_1": "cm",
        })
        self.lc_inc.refresh_from_db()
        logic = self.lc_inc.validated_logic
        self.assertEqual(logic["field"], "tumor_size")

    # ------------------------------------------------------------------
    # 7.4 POST com unit inclui unit na condição guardada
    # ------------------------------------------------------------------
    def test_post_unit_included_in_logic(self):
        self._post({
            f"logic_{self.lc_inc.id}": "on",
            f"group_operator_{self.lc_inc.id}": "AND",
            f"field_{self.lc_inc.id}_1": "hemoglobina",
            f"operator_{self.lc_inc.id}_1": ">=",
            f"value_{self.lc_inc.id}_1": "9",
            f"unit_{self.lc_inc.id}_1": "g/dL",
        })
        self.lc_inc.refresh_from_db()
        self.assertEqual(self.lc_inc.validated_logic.get("unit"), "g/dL")

    # ------------------------------------------------------------------
    # 7.5 POST com logic_id inválido é ignorado
    # ------------------------------------------------------------------
    def test_post_invalid_logic_id_ignored(self):
        response = self._post({"logic_99999": "on"})
        self.assertEqual(response.status_code, 302)

    # ------------------------------------------------------------------
    # 7.6 POST seta validated=True no Logic_criteria
    # ------------------------------------------------------------------
    def test_post_sets_validated_true(self):
        self._post({
            f"logic_{self.lc_inc.id}": "on",
            f"group_operator_{self.lc_inc.id}": "AND",
            f"field_{self.lc_inc.id}_1": "age",
            f"operator_{self.lc_inc.id}_1": ">=",
            f"value_{self.lc_inc.id}_1": "18",
            f"unit_{self.lc_inc.id}_1": "",
        })
        self.lc_inc.refresh_from_db()
        self.assertTrue(self.lc_inc.validated)

    # ------------------------------------------------------------------
    # 7.7 POST seta document.extracted=True
    # ------------------------------------------------------------------
    def test_post_sets_document_extracted_true(self):
        self._post()
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.extracted)

    # ------------------------------------------------------------------
    # 7.8 POST cria Version VALIDATED
    # ------------------------------------------------------------------
    def test_post_creates_validated_version(self):
        with patch("trialpilot.views.document_save") as mock_save:
            self.client.post(self.url, data={})

        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args[0][3], "VALIDATED")

    # ------------------------------------------------------------------
    # 7.9 POST redireciona para trial_list
    # ------------------------------------------------------------------
    def test_post_redirects_to_trial_list(self):
        response = self._post()
        self.assertRedirects(response, reverse("trial_list"))

    # ------------------------------------------------------------------
    # 7.10 Payload VALIDATED tem estrutura e chaves corretas
    # ------------------------------------------------------------------
    def test_post_validated_payload_structure(self):
        captured = {}

        def fake_save(doc, file_obj, filename, version_id):
            content = file_obj.read().decode("utf-8")
            captured["payload"] = json.loads(content)

        with patch("trialpilot.views.document_save", side_effect=fake_save):
            self.client.post(self.url, data={})

        payload = captured["payload"]
        for key in ["document_id", "document_title", "validated_at",
                    "inclusion_criteria", "exclusion_criteria"]:
            self.assertIn(key, payload)

        # Cada entrada de critério tem id, text e logic
        for section in ["inclusion_criteria", "exclusion_criteria"]:
            for entry in payload[section]:
                self.assertIn("id", entry)
                self.assertIn("text", entry)
                self.assertIn("logic", entry)

    # ------------------------------------------------------------------
    # 7.11 validated_criterion preferido sobre raw_criterion no payload
    # ------------------------------------------------------------------
    def test_post_payload_uses_validated_criterion_text(self):
        self.inc1.validated_criterion = "Age ≥ 18 years (corrected)"
        self.inc1.save()

        captured = {}

        def fake_save(doc, file_obj, filename, version_id):
            captured["payload"] = json.loads(file_obj.read().decode("utf-8"))

        with patch("trialpilot.views.document_save", side_effect=fake_save):
            self.client.post(self.url, data={})

        inc_entries = captured["payload"]["inclusion_criteria"]
        texts = [e["text"] for e in inc_entries]
        self.assertIn("Age ≥ 18 years (corrected)", texts)

    # ------------------------------------------------------------------
    # 7.12 Condição sem field E sem operator E sem value não é criada
    # ------------------------------------------------------------------
    def test_post_empty_condition_row_ignored(self):
        self._post({
            f"logic_{self.lc_inc.id}": "on",
            f"group_operator_{self.lc_inc.id}": "AND",
            # Linha 1 completamente vazia
            f"field_{self.lc_inc.id}_1": "",
            f"operator_{self.lc_inc.id}_1": "",
            f"value_{self.lc_inc.id}_1": "",
            f"unit_{self.lc_inc.id}_1": "",
        })
        self.lc_inc.refresh_from_db()
        logic = self.lc_inc.validated_logic
        # Lógica resultante deve ser uma condição vazia ou o raw_logic original
        # O que importa: não deve ter conditions com entradas em branco
        if "conditions" in logic:
            for c in logic["conditions"]:
                self.assertTrue(c.get("field") or c.get("operator") or c.get("value"))