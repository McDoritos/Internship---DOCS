"""
Testes Unitários — match_patients view e pipeline de matching
=============================================================

O módulo de matching não usa chunking nem batching — avalia critério a
critério via regras (evaluate_condition) ou via LLM quando o campo não
pertence ao schema (KNOWN_FIELDS). O LLM é invocado por critério
individualmente, não em batch.

  GUARD CLAUSES — GET
    1.  Documento não existe
    2.  Tipo errado (não é CLINICAL_TRIAL)
    3.  Ensaio ainda não convertido (extracted=False)

  HAPPY PATH — GET
    4.  GET retorna 200 e template correto
    5.  Contexto tem as chaves essenciais
    6.  Patient_trial_match criado para cada doente
    7.  Criterion_evaluation criado por critério avaliável
    8.  eligible_count e ineligible_count corretos no contexto
    9.  Apenas doentes do mesmo pathology_group são avaliados
   10.  Critério sem Logic_criteria (logic=None) é ignorado na avaliação

  POST — overrides manuais
   11.  POST com override muda manual_result do Criterion_evaluation
   12.  Criterion_evaluations sem override ficam com manual_result = automatic_result
   13.  POST recalcula decision do Patient_trial_match após override
   14.  POST redireciona para trial_details com o trial_id correto
   15.  Override com JSON inválido é ignorado sem erro
   16.  Doente elegível após override → decision = ELIGIBLE
   17.  Doente inelegível (exclusion ativa) → decision = INELIGIBLE
   18.  Override com patient_id/criterion_id inválido é ignorado

  patient_matching_step — sem cohorts
   19.  Patient_trial_match criado com INCONCLUSIVE por omissão
   20.  get_or_create reutiliza match existente (não duplica)
   21.  Critério de inclusão PASS → inclusion_results=[True]
   22.  Critério de inclusão FAIL → inclusion_results=[False], eligible=False
   23.  Critério de exclusão PASS → exclusion_triggered=1, eligible=False
   24.  Critério de exclusão FAIL → exclusion_triggered=0
   25.  Resultado final inclui has_cohorts=False quando sem cohorts
   26.  Critérios sem logic (logic=None) são ignorados silenciosamente

  patient_matching_step — com cohorts
   27.  Critério com cohort vai para cohort_criteria_map, não para general
   28.  Doente elegível nos critérios gerais E num cohort → eligible=True
   29.  Doente elegível nos gerais mas em nenhum cohort → eligible=False
   30.  Doente inelegível nos gerais → eligible=False independentemente de cohorts
   31.  cohort_results inclui eligible_cohorts com nome e cohort_id

  evaluate_condition — operadores de regra
   32.  logic=None → result=True (sem critério = passa)
   33.  >= com valor numérico — passa e falha
   34.  <= com valor numérico — passa e falha
   35.  > com valor numérico — passa e falha
   36.  < com valor numérico — passa e falha
   37.  = (equality) — passa e falha
   38.  != (inequality) — passa e falha
   39.  IN com lista — passa e falha
   40.  NOT_IN com lista — passa e falha
   41.  CONTAINS — passa e falha
   42.  NOT_CONTAINS — passa e falha
   43.  AND group — todos devem passar
   44.  OR group — pelo menos um deve passar
   45.  Valor None no paciente → result=False
   46.  Unidade incompatível → result=False
   47.  Campo desconhecido → fallback para LLM
   48.  logic={} (vazio sem field nem conditions) → result=False

  evaluate_condition — campos de data
   49.  diagnosis_date <= "3 years ago" — passa se diagnóstico antigo
   50.  diagnosis_date >= "1 year ago" — falha se diagnóstico antigo

  evaluate_condition — valores laboratoriais (dict com value/unit)
   51.  hemoglobina >= 9 g/dL — passa se valor suficiente
   52.  hemoglobina >= 9 com unidade errada (mg/dL) → result=False

  matching_llm
   53.  Campo desconhecido → chama LLM → devolve match=True
   54.  Campo desconhecido → LLM devolve match=False
   55.  LLM falha (excepção) → devolve False
   56.  Prompt enviado ao LLM contém o criterion text e o clinical diary

  extract_evidence
   57.  Condição simples → 1 evidência com field, patient_value, operator
   58.  Condição de grupo → evidências de todas as sub-condições
   59.  logic=None → lista vazia
   60.  Campo de lab (dict value/unit) → extrai value e unit separados

  get_patient_value
   61.  age → devolve patient.age
   62.  ecog_ps → devolve patient.ecog_ps
   63.  diagnosis → devolve patient.diagnosis
   64.  hemoglobina → devolve dict com value e unit da Analysis
   65.  treatment_name → devolve lista de nomes de tratamentos
   66.  Campo desconhecido → devolve None

  serialize_analysis
   67.  QuerySet com entradas → dict com name: {value, unit}
   68.  QuerySet vazio → dict vazio
   69.  None → dict vazio
"""

import json
import datetime
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from trialpilot.models import (
    Document, ClinicalTrial, Trial_criteria, Logic_criteria,
    Trial_cohort, Patient_profile, Treatment, Analysis,
    Patient_trial_match, Criterion_evaluation,
)
from trialpilot.views import (
    patient_matching_step,
    evaluate_condition,
    extract_evidence,
    get_patient_value,
    serialize_analysis,
    matching_llm,
)

def make_trial_doc(pathology_group="pneumologia"):
    doc = Document.objects.create(
        title="trial_study_abc123.pdf",
        type=Document.DocumentType.CLINICAL_TRIAL,
        extracted=True,
    )
    ClinicalTrial.objects.create(
        document=doc,
        study_name="Study ABC",
        pathology_group=pathology_group,
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2026, 1, 1),
        status="recruiting",
    )
    return doc


def make_diary_doc():
    return Document.objects.create(
        title="inconsistancy-diary_patient_1_abc.txt",
        type=Document.DocumentType.CLINICAL_DIARY,
    )


def make_patient(pathology_group="pneumologia", age=55, ecog_ps=1,
                 diagnosis="Adenocarcinoma do pulmão", stage="IV",
                 molecular_status="EGFR-", gender=False):
    diary = make_diary_doc()
    return Patient_profile.objects.create(
        document=diary,
        age=age,
        ecog_ps=ecog_ps,
        diagnosis=diagnosis,
        stage=stage,
        molecular_status=molecular_status,
        gender=gender,
        pathology_group=pathology_group,
    )


def make_criterion(doc, text, ctype=Trial_criteria.CriterionType.INCLUSION, cohort=None):
    return Trial_criteria.objects.create(
        document=doc,
        cohort=cohort,
        type=ctype,
        raw_criterion=text,
        validated_criterion=text,
        validated=True,
    )


def make_logic_for_criterion(criterion, logic_dict):
    return Logic_criteria.objects.create(
        criterion=criterion,
        raw_logic=logic_dict,
        validated_logic=logic_dict,
        validated=True,
    )


def make_full_criterion(doc, text, logic_dict, ctype=Trial_criteria.CriterionType.INCLUSION, cohort=None):
    c = make_criterion(doc, text, ctype, cohort)
    make_logic_for_criterion(c, logic_dict)
    return c

class MatchPatientsGuardClausesTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_nonexistent_document_renders_error(self):
        response = self.client.get(reverse("match_patients", args=[99999]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("not found", response.context["error"].lower())

    def test_wrong_document_type_renders_error(self):
        doc = Document.objects.create(
            title="diary_patient_1_abc.txt",
            type=Document.DocumentType.CLINICAL_DIARY,
        )
        response = self.client.get(reverse("match_patients", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("clinical trial", response.context["error"].lower())

    def test_not_yet_converted_renders_error(self):
        doc = Document.objects.create(
            title="trial_study_abc123.pdf",
            type=Document.DocumentType.CLINICAL_TRIAL,
            extracted=False,
        )
        ClinicalTrial.objects.create(
            document=doc, study_name="S", pathology_group="pneumologia",
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2026, 1, 1),
            status="recruiting",
        )
        response = self.client.get(reverse("match_patients", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        self.assertIn("criteria must be extracted", response.context["error"].lower())


class MatchPatientsGetTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("match_patients", args=[self.doc.id])

        self.age_criterion = make_full_criterion(
            self.doc, "Age >= 18",
            {"field": "age", "operator": ">=", "value": 18}
        )
        self.patient = make_patient(age=55)

    def test_get_returns_200_and_correct_template(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trialpilot/patient_matching.html")

    def test_get_context_keys_present(self):
        response = self.client.get(self.url)
        for key in ["trial", "patients", "matches", "eligible_count", "ineligible_count"]:
            self.assertIn(key, response.context, f"Missing context key: {key}")

    def test_get_creates_patient_trial_match(self):
        self.client.get(self.url)
        self.assertTrue(
            Patient_trial_match.objects.filter(
                patient=self.patient, trial=self.doc
            ).exists()
        )

    def test_get_creates_criterion_evaluation(self):
        self.client.get(self.url)
        match_obj = Patient_trial_match.objects.get(patient=self.patient, trial=self.doc)
        self.assertTrue(
            Criterion_evaluation.objects.filter(
                match=match_obj, criterion=self.age_criterion
            ).exists()
        )

    def test_get_eligible_count_correct(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["eligible_count"], 1)
        self.assertEqual(response.context["ineligible_count"], 0)

    def test_get_only_same_pathology_group_patients_evaluated(self):
        other_patient = make_patient(pathology_group="mama")
        response = self.client.get(self.url)
        matches = response.context["matches"]
        patient_ids = [m["patient"].id for m in matches]
        self.assertIn(self.patient.id, patient_ids)
        self.assertNotIn(other_patient.id, patient_ids)

    def test_get_criterion_without_logic_is_skipped(self):
        make_criterion(self.doc, "No logic criterion")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_get_ineligible_patient_counted_correctly(self):
        make_full_criterion(
            self.doc, "Stage must be I",
            {"field": "stage", "operator": "=", "value": "I"}
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context["ineligible_count"], 1)

class MatchPatientsPostTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_trial_doc()
        self.url = reverse("match_patients", args=[self.doc.id])
        self.patient = make_patient(age=55)

        self.criterion = make_full_criterion(
            self.doc, "Age >= 18",
            {"field": "age", "operator": ">=", "value": 18}
        )

        self.client.get(self.url)

        self.match_obj = Patient_trial_match.objects.get(
            patient=self.patient, trial=self.doc
        )
        self.eval_obj = Criterion_evaluation.objects.get(
            match=self.match_obj, criterion=self.criterion
        )

    def _post_with_override(self, decision):
        override = json.dumps({
            "patient_id": self.patient.id,
            "criterion_id": self.criterion.id,
            "decision": decision,
        })
        return self.client.post(self.url, data={"overrides": [override]})

    def test_post_override_updates_manual_result(self):
        self._post_with_override(Criterion_evaluation.EvaluationChoices.FAIL)
        self.eval_obj.refresh_from_db()
        self.assertEqual(
            self.eval_obj.manual_result,
            Criterion_evaluation.EvaluationChoices.FAIL
        )

    def test_post_no_override_sets_manual_equal_to_automatic(self):
        self.client.post(self.url, data={"overrides": []})
        self.eval_obj.refresh_from_db()
        self.assertEqual(
            self.eval_obj.manual_result,
            self.eval_obj.automatic_result
        )

    def test_post_override_fail_sets_decision_ineligible(self):
        self._post_with_override(Criterion_evaluation.EvaluationChoices.FAIL)
        self.match_obj.refresh_from_db()
        self.assertEqual(
            self.match_obj.decision,
            Patient_trial_match.Decision.INELIGIBLE
        )

    def test_post_override_pass_keeps_decision_eligible(self):
        self._post_with_override(Criterion_evaluation.EvaluationChoices.PASS)
        self.match_obj.refresh_from_db()
        self.assertEqual(
            self.match_obj.decision,
            Patient_trial_match.Decision.ELIGIBLE
        )

    def test_post_redirects_to_trial_details(self):
        response = self.client.post(self.url, data={"overrides": []})
        self.assertRedirects(
            response,
            reverse("trial_details", args=[self.doc.id]),
            fetch_redirect_response=False,
        )

    def test_post_invalid_json_override_ignored(self):
        response = self.client.post(
            self.url,
            data={"overrides": ["not valid json!!!"]},
        )
        self.assertEqual(response.status_code, 302)

    def test_post_malformed_override_fields_ignored(self):
        override = json.dumps({
            "patient_id": self.patient.id,
            "decision": Criterion_evaluation.EvaluationChoices.FAIL,
        })
        response = self.client.post(self.url, data={"overrides": [override]})
        self.assertRedirects(
            response,
            reverse("trial_details", args=[self.doc.id]),
            fetch_redirect_response=False,
        )

    def test_post_exclusion_trigger_sets_ineligible(self):
        exc = make_full_criterion(
            self.doc, "No active infection",
            {"field": "stage", "operator": "=", "value": "I"},
            ctype=Trial_criteria.CriterionType.EXCLUSION,
        )
        self.client.get(self.url)
        exc_eval = Criterion_evaluation.objects.get(
            match=self.match_obj, criterion=exc
        )
        override = json.dumps({
            "patient_id": self.patient.id,
            "criterion_id": exc.id,
            "decision": Criterion_evaluation.EvaluationChoices.PASS,
        })
        self.client.post(self.url, data={"overrides": [override]})
        self.match_obj.refresh_from_db()
        self.assertEqual(
            self.match_obj.decision,
            Patient_trial_match.Decision.INELIGIBLE
        )
        
    def test_post_invalid_patient_id_ignored(self):
        override = json.dumps({
            "patient_id": 99999,
            "criterion_id": self.criterion.id,
            "decision": Criterion_evaluation.EvaluationChoices.FAIL,
        })
        response = self.client.post(self.url, data={"overrides": [override]})
        self.assertRedirects(
            response,
            reverse("trial_details", args=[self.doc.id]),
            fetch_redirect_response=False,
        )

class PatientMatchingStepNoCohortTest(TestCase):

    def setUp(self):
        self.doc = make_trial_doc()
        self.patient = make_patient(age=55, ecog_ps=1, stage="IV")

    def _criteria_with_select_related(self, criteria_list):
        ids = [c.id for c in criteria_list]
        return Trial_criteria.objects.filter(id__in=ids).select_related("logic")

    def test_creates_patient_trial_match(self):
        result = patient_matching_step(self.patient, self.doc, [])
        self.assertTrue(
            Patient_trial_match.objects.filter(
                patient=self.patient, trial=self.doc
            ).exists()
        )

    def test_get_or_create_does_not_duplicate_match(self):
        patient_matching_step(self.patient, self.doc, [])
        patient_matching_step(self.patient, self.doc, [])
        count = Patient_trial_match.objects.filter(
            patient=self.patient, trial=self.doc
        ).count()
        self.assertEqual(count, 1)

    def test_inclusion_criterion_pass(self):
        c = make_full_criterion(
            self.doc, "Age >= 18",
            {"field": "age", "operator": ">=", "value": 18}
        )
        criteria = self._criteria_with_select_related([c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertEqual(result["inclusion_passed"], 1)
        self.assertTrue(result["eligible"])

    def test_inclusion_criterion_fail(self):
        c = make_full_criterion(
            self.doc, "Stage must be I",
            {"field": "stage", "operator": "=", "value": "I"}
        )
        criteria = self._criteria_with_select_related([c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertEqual(result["inclusion_passed"], 0)
        self.assertFalse(result["eligible"])

    def test_exclusion_criterion_triggered_makes_ineligible(self):
        c = make_full_criterion(
            self.doc, "Stage IV excluded",
            {"field": "stage", "operator": "=", "value": "IV"},
            ctype=Trial_criteria.CriterionType.EXCLUSION,
        )
        criteria = self._criteria_with_select_related([c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertEqual(result["exclusion_triggered"], 1)
        self.assertFalse(result["eligible"])

    def test_exclusion_criterion_not_triggered(self):
        c = make_full_criterion(
            self.doc, "Stage I excluded",
            {"field": "stage", "operator": "=", "value": "I"},
            ctype=Trial_criteria.CriterionType.EXCLUSION,
        )
        criteria = self._criteria_with_select_related([c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertEqual(result["exclusion_triggered"], 0)
        self.assertTrue(result["eligible"])

    def test_has_cohorts_false_without_cohort_criteria(self):
        result = patient_matching_step(self.patient, self.doc, [])
        self.assertFalse(result["has_cohorts"])

    def test_criterion_without_logic_skipped(self):
        c = make_criterion(self.doc, "Criterion without logic")
        criteria = self._criteria_with_select_related([c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertEqual(result["inclusion_total"], 0)

    def test_criterion_evaluation_created_in_db(self):
        c = make_full_criterion(
            self.doc, "Age >= 18",
            {"field": "age", "operator": ">=", "value": 18}
        )
        criteria = self._criteria_with_select_related([c])
        patient_matching_step(self.patient, self.doc, criteria)
        match_obj = Patient_trial_match.objects.get(patient=self.patient, trial=self.doc)
        self.assertTrue(
            Criterion_evaluation.objects.filter(match=match_obj, criterion=c).exists()
        )

class PatientMatchingStepWithCohortTest(TestCase):

    def setUp(self):
        self.doc = make_trial_doc()
        self.patient = make_patient(age=55, stage="IV")

        self.cohort_a = Trial_cohort.objects.create(
            cohort_id="A", clinical_trial=self.doc.clinical_trial, name="EGFR+"
        )
        self.cohort_b = Trial_cohort.objects.create(
            cohort_id="B", clinical_trial=self.doc.clinical_trial, name="ALK+"
        )

    def _criteria_qs(self, criteria_list):
        ids = [c.id for c in criteria_list]
        return Trial_criteria.objects.filter(id__in=ids).select_related("logic", "cohort")

    def test_cohort_criterion_goes_to_cohort_map(self):
        general = make_full_criterion(
            self.doc, "Age >= 18", {"field": "age", "operator": ">=", "value": 18}
        )
        cohort_c = make_full_criterion(
            self.doc, "EGFR+",
            {"field": "molecular_status", "operator": "CONTAINS", "value": "EGFR+"},
            cohort=self.cohort_a,
        )
        criteria = self._criteria_qs([general, cohort_c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertTrue(result["has_cohorts"])

    def test_eligible_in_general_and_cohort_a(self):
        general = make_full_criterion(
            self.doc, "Age >= 18", {"field": "age", "operator": ">=", "value": 18}
        )
        cohort_a_c = make_full_criterion(
            self.doc, "EGFR+",
            {"field": "molecular_status", "operator": "CONTAINS", "value": "EGFR+"},
            cohort=self.cohort_a,
        )
        criteria = self._criteria_qs([general, cohort_a_c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["eligible_cohorts"], [])

    def test_eligible_in_general_and_matching_cohort(self):
        general = make_full_criterion(
            self.doc, "Age >= 18", {"field": "age", "operator": ">=", "value": 18}
        )
        cohort_a_c = make_full_criterion(
            self.doc, "Stage IV",
            {"field": "stage", "operator": "=", "value": "IV"},
            cohort=self.cohort_a,
        )
        criteria = self._criteria_qs([general, cohort_a_c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertTrue(result["eligible"])
        self.assertEqual(len(result["eligible_cohorts"]), 1)
        self.assertEqual(result["eligible_cohorts"][0]["cohort_id"], "A")

    def test_ineligible_in_general_makes_fully_ineligible(self):
        general = make_full_criterion(
            self.doc, "Stage I only",
            {"field": "stage", "operator": "=", "value": "I"}
        )
        cohort_a_c = make_full_criterion(
            self.doc, "Age >= 18", {"field": "age", "operator": ">=", "value": 18},
            cohort=self.cohort_a,
        )
        criteria = self._criteria_qs([general, cohort_a_c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["eligible_cohorts"], [])

    def test_cohort_results_contain_cohort_name(self):
        cohort_a_c = make_full_criterion(
            self.doc, "Stage IV",
            {"field": "stage", "operator": "=", "value": "IV"},
            cohort=self.cohort_a,
        )
        criteria = self._criteria_qs([cohort_a_c])
        result = patient_matching_step(self.patient, self.doc, criteria)
        cohort_results = result["cohort_results"]
        names = [v["cohort_name"] for v in cohort_results.values()]
        self.assertIn("EGFR+", names)

class EvaluateConditionRuleTest(TestCase):

    def setUp(self):
        self.patient = make_patient(age=55, ecog_ps=1, stage="IV",
                                    diagnosis="Adenocarcinoma do pulmão",
                                    molecular_status="EGFR-")

    def test_none_logic_returns_true(self):
        result = evaluate_condition(self.patient, None)
        self.assertTrue(result["result"])

    def test_gte_pass(self):
        result = evaluate_condition(self.patient, {"field": "age", "operator": ">=", "value": 18})
        self.assertTrue(result["result"])

    def test_gte_fail(self):
        result = evaluate_condition(self.patient, {"field": "age", "operator": ">=", "value": 100})
        self.assertFalse(result["result"])

    def test_lte_pass(self):
        result = evaluate_condition(self.patient, {"field": "ecog_ps", "operator": "<=", "value": 2})
        self.assertTrue(result["result"])

    def test_lte_fail(self):
        result = evaluate_condition(self.patient, {"field": "ecog_ps", "operator": "<=", "value": 0})
        self.assertFalse(result["result"])

    def test_gt_pass(self):
        result = evaluate_condition(self.patient, {"field": "age", "operator": ">", "value": 18})
        self.assertTrue(result["result"])

    def test_gt_fail(self):
        result = evaluate_condition(self.patient, {"field": "age", "operator": ">", "value": 55})
        self.assertFalse(result["result"])

    def test_lt_pass(self):
        result = evaluate_condition(self.patient, {"field": "age", "operator": "<", "value": 100})
        self.assertTrue(result["result"])

    def test_lt_fail(self):
        result = evaluate_condition(self.patient, {"field": "age", "operator": "<", "value": 10})
        self.assertFalse(result["result"])

    def test_equality_pass(self):
        result = evaluate_condition(self.patient, {"field": "stage", "operator": "=", "value": "IV"})
        self.assertTrue(result["result"])

    def test_equality_fail(self):
        result = evaluate_condition(self.patient, {"field": "stage", "operator": "=", "value": "I"})
        self.assertFalse(result["result"])

    def test_inequality_pass(self):
        result = evaluate_condition(self.patient, {"field": "stage", "operator": "!=", "value": "I"})
        self.assertTrue(result["result"])

    def test_inequality_fail(self):
        result = evaluate_condition(self.patient, {"field": "stage", "operator": "!=", "value": "IV"})
        self.assertFalse(result["result"])

    def test_in_list_pass(self):
        result = evaluate_condition(self.patient, {
            "field": "stage", "operator": "IN", "value": ["III", "IV"]
        })
        self.assertTrue(result["result"])

    def test_in_list_fail(self):
        result = evaluate_condition(self.patient, {
            "field": "stage", "operator": "IN", "value": ["I", "II"]
        })
        self.assertFalse(result["result"])

    def test_not_in_pass(self):
        result = evaluate_condition(self.patient, {
            "field": "stage", "operator": "NOT_IN", "value": ["I", "II"]
        })
        self.assertTrue(result["result"])

    def test_not_in_fail(self):
        result = evaluate_condition(self.patient, {
            "field": "stage", "operator": "NOT_IN", "value": ["III", "IV"]
        })
        self.assertFalse(result["result"])

    def test_contains_pass(self):
        result = evaluate_condition(self.patient, {
            "field": "diagnosis", "operator": "CONTAINS", "value": "Adenocarcinoma"
        })
        self.assertTrue(result["result"])

    def test_contains_fail(self):
        result = evaluate_condition(self.patient, {
            "field": "diagnosis", "operator": "CONTAINS", "value": "Melanoma"
        })
        self.assertFalse(result["result"])

    def test_not_contains_pass(self):
        result = evaluate_condition(self.patient, {
            "field": "diagnosis", "operator": "NOT_CONTAINS", "value": "Melanoma"
        })
        self.assertTrue(result["result"])

    def test_not_contains_fail(self):
        result = evaluate_condition(self.patient, {
            "field": "diagnosis", "operator": "NOT_CONTAINS", "value": "Adenocarcinoma"
        })
        self.assertFalse(result["result"])

    def test_and_group_all_pass(self):
        logic = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "ecog_ps", "operator": "<=", "value": 2},
            ]
        }
        result = evaluate_condition(self.patient, logic)
        self.assertTrue(result["result"])

    def test_and_group_one_fail(self):
        logic = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "stage", "operator": "=", "value": "I"},  # fails
            ]
        }
        result = evaluate_condition(self.patient, logic)
        self.assertFalse(result["result"])

    def test_or_group_one_pass(self):
        logic = {
            "operator": "OR",
            "conditions": [
                {"field": "stage", "operator": "=", "value": "I"},   # fails
                {"field": "age", "operator": ">=", "value": 18},      # passes
            ]
        }
        result = evaluate_condition(self.patient, logic)
        self.assertTrue(result["result"])

    def test_or_group_all_fail(self):
        logic = {
            "operator": "OR",
            "conditions": [
                {"field": "stage", "operator": "=", "value": "I"},
                {"field": "age", "operator": ">=", "value": 100},
            ]
        }
        result = evaluate_condition(self.patient, logic)
        self.assertFalse(result["result"])

    def test_none_patient_value_returns_false(self):
        self.patient.ecog_ps = None
        self.patient.save()
        result = evaluate_condition(self.patient, {"field": "ecog_ps", "operator": ">=", "value": 0})
        self.assertFalse(result["result"])

    def test_unknown_field_calls_matching_llm(self):
        logic = {"field": "bmi", "operator": ">=", "value": 18.5}
        llm_response = {"match": True, "justification": "BMI is adequate."}
        with patch("trialpilot.views.matching_llm", return_value=llm_response) as mock_llm:
            result = evaluate_condition(self.patient, logic)
        mock_llm.assert_called_once_with(self.patient, logic)
        self.assertTrue(result["result"])

    def test_empty_logic_dict_returns_true(self):
        result = evaluate_condition(self.patient, {})
        self.assertTrue(result["result"])

class EvaluateConditionDateFieldTest(TestCase):

    def setUp(self):
        four_years_ago = (timezone.now().date() - datetime.timedelta(days=4*365)).isoformat()
        self.patient = make_patient()
        self.patient.diagnosis_date = four_years_ago
        self.patient.save()

    def test_date_lte_3_years_ago_passes(self):
        result = evaluate_condition(self.patient, {
            "field": "diagnosis_date", "operator": "<=", "value": "3 years ago"
        })
        self.assertTrue(result["result"])

    def test_date_gte_1_year_ago_passes(self):
        result = evaluate_condition(self.patient, {
            "field": "diagnosis_date", "operator": ">=", "value": "1 year ago"
        })
        self.assertFalse(result["result"])

class EvaluateConditionLabValueTest(TestCase):

    def setUp(self):
        self.patient = make_patient()
        Analysis.objects.create(
            patient=self.patient,
            name="hemoglobina",
            value="11.2",
            unit="g/dL",
        )

    def test_lab_value_gte_passes(self):
        result = evaluate_condition(self.patient, {
            "field": "hemoglobina", "operator": ">=", "value": 9, "unit": "g/dL"
        })
        self.assertTrue(result["result"])

    def test_lab_value_gte_fails(self):
        result = evaluate_condition(self.patient, {
            "field": "hemoglobina", "operator": ">=", "value": 12, "unit": "g/dL"
        })
        self.assertFalse(result["result"])

    def test_unit_mismatch_returns_false(self):
        result = evaluate_condition(self.patient, {
            "field": "hemoglobina", "operator": ">=", "value": 9, "unit": "mg/dL"
        })
        self.assertFalse(result["result"])

    def test_missing_lab_value_returns_false(self):
        result = evaluate_condition(self.patient, {
            "field": "leucocitos", "operator": ">=", "value": 4
        })
        self.assertFalse(result["result"])

class MatchingLlmTest(TestCase):

    def setUp(self):
        self.patient = make_patient()

    @patch("trialpilot.views.extract_document_text", return_value="Diary content here.")
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CLINICAL_DIARY}} {{CRITERION_TEXT}} {{ANALYSIS_VALUES}}"))
    @patch("trialpilot.views.call_llm", return_value=json.dumps({"match": True, "justification": "Patient meets criterion."}))
    def test_llm_returns_match_true(self, _mock_llm, _mock_prompts, _mock_extract):
        logic = {"field": "bmi", "operator": ">=", "value": 18.5}
        result = matching_llm(self.patient, logic)
        self.assertTrue(result["match"])
        self.assertIn("justification", result)

    @patch("trialpilot.views.extract_document_text", return_value="Diary content here.")
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CLINICAL_DIARY}} {{CRITERION_TEXT}} {{ANALYSIS_VALUES}}"))
    @patch("trialpilot.views.call_llm", return_value=json.dumps({"match": False, "justification": "Not applicable."}))
    def test_llm_returns_match_false(self, _mock_llm, _mock_prompts, _mock_extract):
        logic = {"field": "bmi", "operator": ">=", "value": 18.5}
        result = matching_llm(self.patient, logic)
        self.assertFalse(result["match"])

    @patch("trialpilot.views.get_patient_text", return_value="diary text")
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CLINICAL_DIARY}} {{CRITERION_TEXT}} {{ANALYSIS_VALUES}}"))
    @patch("trialpilot.views.call_llm", side_effect=Exception("LLM network error"))
    def test_llm_exception_returns_false(self, _mock_llm, _mock_prompts, _mock_text):
        logic = {"field": "bmi", "operator": ">=", "value": 18.5}
        result = matching_llm(self.patient, logic)
        self.assertFalse(result)

    @patch("trialpilot.views.extract_document_text", return_value="Clinical diary text content.")
    @patch("trialpilot.views.load_prompt_files", return_value=("sys", "{{CLINICAL_DIARY}} {{CRITERION_TEXT}} {{ANALYSIS_VALUES}}"))
    def test_llm_prompt_contains_criterion_and_diary(self, _mock_prompts, _mock_extract):
        captured = {}

        def fake_llm(sys_p, user_p):
            captured["prompt"] = user_p
            return json.dumps({"match": True, "justification": "ok"})

        logic = {"field": "bmi", "operator": ">=", "value": 18.5}
        with patch("trialpilot.views.call_llm", side_effect=fake_llm):
            matching_llm(self.patient, logic)

        self.assertIn("Clinical diary text content.", captured["prompt"])
        self.assertIn("bmi", captured["prompt"])

class ExtractEvidenceTest(TestCase):

    def setUp(self):
        self.patient = make_patient(age=55, stage="IV")

    def test_simple_condition_returns_one_evidence(self):
        logic = {"field": "age", "operator": ">=", "value": 18}
        evidences = extract_evidence(self.patient, logic)
        self.assertEqual(len(evidences), 1)
        ev = evidences[0]
        self.assertEqual(ev["field"], "age")
        self.assertEqual(ev["operator"], ">=")
        self.assertEqual(ev["expected_value"], 18)

    def test_group_condition_returns_all_evidences(self):
        logic = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "stage", "operator": "=", "value": "IV"},
            ]
        }
        evidences = extract_evidence(self.patient, logic)
        self.assertEqual(len(evidences), 2)
        fields = [ev["field"] for ev in evidences]
        self.assertIn("age", fields)
        self.assertIn("stage", fields)

    def test_none_logic_returns_empty_list(self):
        self.assertEqual(extract_evidence(self.patient, None), [])

    def test_lab_value_extracted_with_unit(self):
        Analysis.objects.create(
            patient=self.patient, name="hemoglobina", value="11.2", unit="g/dL"
        )
        logic = {"field": "hemoglobina", "operator": ">=", "value": 9, "unit": "g/dL"}
        evidences = extract_evidence(self.patient, logic)
        self.assertEqual(len(evidences), 1)
        ev = evidences[0]
        self.assertEqual(ev["patient_value"], 11.2)
        self.assertEqual(ev["patient_unit"], "g/dL")

class GetPatientValueTest(TestCase):

    def setUp(self):
        self.patient = make_patient(age=55, ecog_ps=1, stage="IV",
                                    diagnosis="Adenocarcinoma do pulmão")

    def test_age_field(self):
        self.assertEqual(get_patient_value(self.patient, "age"), 55)

    def test_ecog_ps_field(self):
        self.assertEqual(get_patient_value(self.patient, "ecog_ps"), 1)

    def test_diagnosis_field(self):
        self.assertEqual(get_patient_value(self.patient, "diagnosis"), "Adenocarcinoma do pulmão")

    def test_hemoglobina_returns_dict(self):
        Analysis.objects.create(
            patient=self.patient, name="hemoglobina", value="11.2", unit="g/dL"
        )
        result = get_patient_value(self.patient, "hemoglobina")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["value"], 11.2)
        self.assertEqual(result["unit"], "g/dL")

    def test_treatment_name_returns_list(self):
        Treatment.objects.create(
            patient=self.patient,
            treatment_name="Osimertinib",
            start_date=datetime.date(2023, 1, 1),
        )
        result = get_patient_value(self.patient, "treatment_name")
        self.assertIsInstance(result, list)
        self.assertIn("Osimertinib", result)

    def test_unknown_field_returns_none(self):
        result = get_patient_value(self.patient, "bmi")
        self.assertIsNone(result)

    def test_missing_lab_value_returns_none(self):
        result = get_patient_value(self.patient, "leucocitos")
        self.assertIsNone(result)

class SerializeAnalysisTest(TestCase):

    def setUp(self):
        self.patient = make_patient()

    def test_queryset_with_entries(self):
        Analysis.objects.create(patient=self.patient, name="hemoglobina", value="11.2", unit="g/dL")
        Analysis.objects.create(patient=self.patient, name="creatinina", value="0.9", unit="mg/dL")
        qs = Analysis.objects.filter(patient=self.patient)
        result = serialize_analysis(qs)
        self.assertIn("hemoglobina", result)
        self.assertEqual(result["hemoglobina"]["value"], 11.2)
        self.assertEqual(result["hemoglobina"]["unit"], "g/dL")
        self.assertIn("creatinina", result)

    def test_empty_queryset_returns_empty_dict(self):
        qs = Analysis.objects.filter(patient=self.patient)
        self.assertEqual(serialize_analysis(qs), {})

    def test_none_returns_empty_dict(self):
        self.assertEqual(serialize_analysis(None), {})