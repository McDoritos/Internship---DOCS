import json
import datetime
from io import BytesIO
from unittest.mock import patch, MagicMock
 
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import override_settings
from django.core.files.storage import FileSystemStorage
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os

from trialpilot.forms import UploadDocumentForm, UploadTrialForm
from trialpilot.models import (
    Document, Patient_profile, Treatment, Analysis,
    ClinicalTrial, Trial_criteria, Logic_criteria,
    Patient_trial_match, Version, Criterion_evaluation, Trial_cohort,
)
from trialpilot.views import (
    normalize_text, parse_gender, clean_value, format_logic,
    extract_json_from_response, deduplicate, is_similar, normalize,
    split_text_into_chunks, normalize_value, normalize_unit,
    safe_float, parse_date, parse_relative_date, evaluate_condition,
    add_analysis, extract_lab_parameters, parse_possible_list,
    get_any,
)

# Helpers

def make_pdf_file(name="test.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake content", content_type="application/pdf")

def make_txt_file(name="test.txt", content=b"hello world"):
    return SimpleUploadedFile(name, content, content_type="text/plain")

def make_document(doc_type=Document.DocumentType.CLINICAL_DIARY, title="diary_abc123.txt"):
    return Document.objects.create(title=title, type=doc_type)
 
def make_clinical_trial_document(title="trial_abc123.pdf"):
    doc = Document.objects.create(
        title=title,
        type=Document.DocumentType.CLINICAL_TRIAL
    )
    ClinicalTrial.objects.create(
        document=doc,
        study_name="Study A",
        pathology_group="mama",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2025, 1, 1),
        status="recruiting",
    )
    return doc

def make_patient(document):
    return Patient_profile.objects.create(
        document=document,
        age=45,
        ecog_ps=1,
        diagnosis="NSCLC",
        stage="IV",
        molecular_status="EGFR-",
        gender=True,
        pathology_group="pneumologia",
    )
    
# Forms

class UploadDocumentFormTest(TestCase):
 
    def test_valid_pdf_upload(self):
        form = UploadDocumentForm(
            data={"type": False},
            files={"file": make_pdf_file()}
        )
        self.assertTrue(form.is_valid(), form.errors)
 
    def test_valid_txt_upload(self):
        form = UploadDocumentForm(
            data={"type": False},
            files={"file": make_txt_file()}
        )
        self.assertTrue(form.is_valid(), form.errors)
 
    def test_invalid_extension(self):
        bad_file = SimpleUploadedFile("report.docx", b"data", content_type="application/msword")
        form = UploadDocumentForm(data={"type": False}, files={"file": bad_file})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)
 
    def test_missing_file(self):
        form = UploadDocumentForm(data={"type": False}, files={})
        self.assertFalse(form.is_valid())
 
    def test_type_boolean_field_defaults_false(self):
        form = UploadDocumentForm(
            data={},          # type omitted → BooleanField required=False → False
            files={"file": make_txt_file()}
        )
        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data["type"])
 
 
class UploadTrialFormTest(TestCase):
 
    def _base_data(self, **overrides):
        data = {
            "type": False,
            "study_name": "Trial X",
            "pathology_group": "mama",
            "start_date": "2024-01-01",
            "end_date": "2025-01-01",
            "status": "recruiting",
        }
        data.update(overrides)
        return data
 
    def test_valid_form(self):
        form = UploadTrialForm(
            data=self._base_data(),
            files={"file": make_pdf_file()}
        )
        self.assertTrue(form.is_valid(), form.errors)
 
    def test_missing_study_name(self):
        data = self._base_data()
        data.pop("study_name")
        form = UploadTrialForm(data=data, files={"file": make_pdf_file()})
        self.assertFalse(form.is_valid())
        self.assertIn("study_name", form.errors)
 
    def test_invalid_pathology_group(self):
        form = UploadTrialForm(
            data=self._base_data(pathology_group="invalid_group"),
            files={"file": make_pdf_file()}
        )
        self.assertFalse(form.is_valid())
 
    def test_invalid_status(self):
        form = UploadTrialForm(
            data=self._base_data(status="unknown"),
            files={"file": make_pdf_file()}
        )
        self.assertFalse(form.is_valid())
 
    def test_invalid_file_extension(self):
        bad_file = SimpleUploadedFile("report.csv", b"data", content_type="text/csv")
        form = UploadTrialForm(
            data=self._base_data(),
            files={"file": bad_file}
        )
        self.assertFalse(form.is_valid())
 
    def test_all_pathology_group_choices_valid(self):
        valid_groups = [
            "cabeca_pescoco", "dermatologia", "digestivo", "ginecologia",
            "mama", "oncologia_pediatrica", "pele", "pneumologia", "snc", "tne"
        ]
        for group in valid_groups:
            form = UploadTrialForm(
                data=self._base_data(pathology_group=group),
                files={"file": make_pdf_file()}
            )
            self.assertTrue(form.is_valid(), f"Group '{group}' should be valid: {form.errors}")
 
    def test_all_status_choices_valid(self):
        for status in ["recruiting", "closed", "not_yet", "completed"]:
            form = UploadTrialForm(
                data=self._base_data(status=status),
                files={"file": make_pdf_file()}
            )
            self.assertTrue(form.is_valid(), f"Status '{status}' should be valid: {form.errors}")
            
# Auxiliar functions

class NormalizeTextTest(TestCase):
 
    def test_removes_extra_spaces(self):
        result = normalize_text("hello   world")
        self.assertEqual(result, "hello world")
 
    def test_removes_extra_newlines(self):
        result = normalize_text("line1\n\n\n\nline2")
        self.assertNotIn("\n\n\n", result)
 
    def test_strips_whitespace(self):
        result = normalize_text("  hello  ")
        self.assertEqual(result, "hello")
 
    def test_unicode_normalization(self):
        # NFKC should normalize ligatures etc.
        result = normalize_text("\ufb01le")   # ﬁ → fi
        self.assertEqual(result, "file")
 
    def test_normalizes_dashes(self):
        result = normalize_text("word\u2013word")  # en-dash → hyphen
        self.assertIn("-", result)
 
 
class ParseGenderTest(TestCase):
 
    def test_male_english(self):
        self.assertTrue(parse_gender("male"))
        self.assertTrue(parse_gender("M"))
 
    def test_female_english(self):
        self.assertFalse(parse_gender("female"))
        self.assertFalse(parse_gender("F"))
 
    def test_male_portuguese(self):
        self.assertTrue(parse_gender("masculino"))
 
    def test_female_portuguese(self):
        self.assertFalse(parse_gender("feminino"))
 
    def test_none_input(self):
        self.assertIsNone(parse_gender(None))
 
    def test_unknown_string(self):
        self.assertIsNone(parse_gender("unknown"))
 
    def test_strips_spaces(self):
        self.assertTrue(parse_gender("  male  "))
 
 
class CleanValueTest(TestCase):
 
    def test_none_string_returns_none(self):
        self.assertIsNone(clean_value("None"))
 
    def test_empty_string_returns_none(self):
        self.assertIsNone(clean_value(""))
 
    def test_null_string_returns_none(self):
        self.assertIsNone(clean_value("null"))
 
    def test_none_returns_none(self):
        self.assertIsNone(clean_value(None))
 
    def test_valid_value_returned(self):
        self.assertEqual(clean_value("hello"), "hello")
        self.assertEqual(clean_value(42), 42)
 
 
class FormatLogicTest(TestCase):
 
    def test_simple_condition(self):
        logic = {"field": "age", "operator": ">=", "value": 18}
        self.assertEqual(format_logic(logic), "age >= 18")
 
    def test_nested_and(self):
        logic = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "ecog_ps", "operator": "<=", "value": 1},
            ]
        }
        result = format_logic(logic)
        self.assertIn("AND", result)
        self.assertIn("age >= 18", result)
 
    def test_nested_or(self):
        logic = {
            "operator": "OR",
            "conditions": [
                {"field": "diagnosis", "operator": "=", "value": "NSCLC"},
                {"field": "stage", "operator": "=", "value": "IV"},
            ]
        }
        result = format_logic(logic)
        self.assertIn("OR", result)
 
    def test_none_logic_returns_none(self):
        self.assertIsNone(format_logic(None))
 
 
class ExtractJsonFromResponseTest(TestCase):
 
    def test_plain_json(self):
        raw = '{"key": "value"}'
        result = extract_json_from_response(raw)
        self.assertEqual(result["key"], "value")
 
    def test_json_with_markdown_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = extract_json_from_response(raw)
        self.assertEqual(result["key"], "value")
 
    def test_json_embedded_in_text(self):
        raw = 'Here is the result: {"key": "value"} - done.'
        result = extract_json_from_response(raw)
        self.assertEqual(result["key"], "value")
 
    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            extract_json_from_response("")
 
    def test_invalid_json_raises(self):
        with self.assertRaises((ValueError, Exception)):
            extract_json_from_response("not json at all!!!")
 
 
class DeduplicateTest(TestCase):
 
    def test_removes_exact_duplicates(self):
        criteria = ["Age >= 18", "Age >= 18", "ECOG 0-1"]
        result = deduplicate(criteria)
        self.assertEqual(len(result), 2)
 
    def test_removes_similar_entries(self):
        criteria = [
            "Age >= 18 years",
            "Age >= 18 years.",   # very similar
            "ECOG 0-1"
        ]
        result = deduplicate(criteria)
        # The two age entries are ≥0.92 similar → only one kept
        self.assertLessEqual(len(result), 2)
 
    def test_keeps_distinct_entries(self):
        criteria = ["Age >= 18", "ECOG 0", "Stage IV"]
        result = deduplicate(criteria)
        self.assertEqual(len(result), 3)
 
    def test_handles_dict_entries(self):
        criteria = [
            {"text": "Age >= 18"},
            {"text": "Age >= 18"},
        ]
        result = deduplicate(criteria)
        self.assertEqual(len(result), 1)
 
 
class SplitTextIntoChunksTest(TestCase):
 
    def test_single_chunk_for_short_text(self):
        text = "Line 1\nLine 2\n"
        chunks = split_text_into_chunks(text, max_chars=1000)
        self.assertEqual(len(chunks), 1)
 
    def test_multiple_chunks_for_long_text(self):
        # Build a text longer than max_chars
        text = ("A" * 100 + "\n") * 50   # 5050 chars
        chunks = split_text_into_chunks(text, max_chars=500)
        self.assertGreater(len(chunks), 1)
 
    def test_no_empty_chunks(self):
        text = "Para 1\nPara 2\nPara 3\n"
        chunks = split_text_into_chunks(text, max_chars=20)
        for chunk in chunks:
            self.assertTrue(chunk.strip())
 
 
class SafeFloatTest(TestCase):
 
    def test_integer_string(self):
        self.assertEqual(safe_float("42"), 42.0)
 
    def test_float_string(self):
        self.assertAlmostEqual(safe_float("3.14"), 3.14)
 
    def test_invalid_returns_none(self):
        self.assertIsNone(safe_float("abc"))
 
    def test_none_returns_none(self):
        self.assertIsNone(safe_float(None))
 
 
class ParseDateTest(TestCase):
 
    def test_iso_format(self):
        result = parse_date("2024-06-15")
        self.assertEqual(result, datetime.date(2024, 6, 15))
 
    def test_long_month_format(self):
        result = parse_date("June 15, 2024")
        self.assertEqual(result, datetime.date(2024, 6, 15))
 
    def test_none_returns_none(self):
        self.assertIsNone(parse_date(None))
 
    def test_invalid_string_returns_none(self):
        self.assertIsNone(parse_date("not a date"))
 
 
class ParseRelativeDateTest(TestCase):
 
    def test_years_ago(self):
        result = parse_relative_date("3 years ago")
        self.assertIsNotNone(result)
        # Should be approximately 3 years before today
        expected = timezone.now().date().replace(year=timezone.now().year - 3)
        self.assertEqual(result.year, expected.year)
 
    def test_months_ago(self):
        result = parse_relative_date("6 months ago")
        self.assertIsNotNone(result)
 
    def test_weeks_ago(self):
        result = parse_relative_date("2 weeks ago")
        self.assertIsNotNone(result)
 
    def test_none_returns_none(self):
        self.assertIsNone(parse_relative_date(None))
 
    def test_invalid_string_returns_none(self):
        self.assertIsNone(parse_relative_date("recently"))
 
 
class NormalizeValueTest(TestCase):
 
    def test_numeric_string(self):
        self.assertEqual(normalize_value("42"), 42.0)
 
    def test_non_numeric(self):
        self.assertEqual(normalize_value("NSCLC"), "nsclc")
 
    def test_strips_and_lowercases(self):
        self.assertEqual(normalize_value("  Stage IV  "), "stage iv")
 
 
class NormalizeUnitTest(TestCase):
 
    def test_removes_spaces(self):
        self.assertEqual(normalize_unit("g / dL"), "g/dl")
 
    def test_removes_leading_x(self):
        result = normalize_unit("x10^9/L")
        self.assertFalse(result.startswith("x"))
 
    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_unit(None), "")
 
    def test_case_insensitive(self):
        self.assertEqual(normalize_unit("G/DL"), normalize_unit("g/dl"))
 
 
class ParsePossibleListTest(TestCase):
 
    def test_bool_passthrough(self):
        self.assertTrue(parse_possible_list(True))
        self.assertFalse(parse_possible_list(False))
 
    def test_list_string_parsed(self):
        result = parse_possible_list('["a", "b", "c"]')
        self.assertEqual(result, ["a", "b", "c"])
 
    def test_plain_string_returned(self):
        self.assertEqual(parse_possible_list("hello"), "hello")
 
 
class GetAnyTest(TestCase):
 
    def test_returns_first_found(self):
        d = {"b": 2, "c": 3}
        self.assertEqual(get_any(d, "a", "b", "c"), 2)
 
    def test_returns_default_when_none_found(self):
        d = {"x": 1}
        self.assertIsNone(get_any(d, "a", "b"))
 
    def test_custom_default(self):
        d = {}
        self.assertEqual(get_any(d, "a", default="fallback"), "fallback")
 
 
class EvaluateConditionTest(TestCase):
    """
    Tests for the evaluate_condition function.
    Uses a mock patient object to avoid needing real DB records.
    """
 
    def _make_patient(self, **attrs):
        patient = MagicMock()
        for k, v in attrs.items():
            setattr(patient, k, v)
        return patient
 
    def test_empty_logic_returns_true(self):
        patient = self._make_patient()
        result = evaluate_condition(patient, None)
        self.assertTrue(result["result"])
 
    def test_age_gte_passes(self):
        patient = self._make_patient(age=65)
        logic = {"field": "age", "operator": ">=", "value": 18}
        with patch("trialpilot.views.get_patient_value", return_value=65):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_age_gte_fails(self):
        patient = self._make_patient(age=10)
        logic = {"field": "age", "operator": ">=", "value": 18}
        with patch("trialpilot.views.get_patient_value", return_value=10):
            result = evaluate_condition(patient, logic)
        self.assertFalse(result["result"])
 
    def test_equality_operator(self):
        patient = self._make_patient()
        logic = {"field": "diagnosis", "operator": "=", "value": "NSCLC"}
        with patch("trialpilot.views.get_patient_value", return_value="NSCLC"):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_inequality_operator(self):
        patient = self._make_patient()
        logic = {"field": "diagnosis", "operator": "!=", "value": "SCLC"}
        with patch("trialpilot.views.get_patient_value", return_value="NSCLC"):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_in_operator_list(self):
        patient = self._make_patient()
        logic = {"field": "stage", "operator": "IN", "value": ["III", "IV"]}
        with patch("trialpilot.views.get_patient_value", return_value="IV"):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_not_in_operator(self):
        patient = self._make_patient()
        logic = {"field": "stage", "operator": "NOT_IN", "value": ["I", "II"]}
        with patch("trialpilot.views.get_patient_value", return_value="IV"):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_contains_operator(self):
        patient = self._make_patient()
        logic = {"field": "molecular_status", "operator": "CONTAINS", "value": "EGFR"}
        with patch("trialpilot.views.get_patient_value", return_value="EGFR positive"):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_and_logic_all_true(self):
        patient = self._make_patient()
        logic = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "ecog_ps", "operator": "<=", "value": 1},
            ]
        }
        def mock_resolver(p, field):
            return 65 if field == "age" else 0
        with patch("trialpilot.views.get_patient_value", side_effect=mock_resolver):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_and_logic_one_fails(self):
        patient = self._make_patient()
        logic = {
            "operator": "AND",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "ecog_ps", "operator": "<=", "value": 1},
            ]
        }
        def mock_resolver(p, field):
            return 65 if field == "age" else 3   # ecog 3 > 1 → fails
        with patch("trialpilot.views.get_patient_value", side_effect=mock_resolver):
            result = evaluate_condition(patient, logic)
        self.assertFalse(result["result"])
 
    def test_or_logic_one_true(self):
        patient = self._make_patient()
        logic = {
            "operator": "OR",
            "conditions": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "ecog_ps", "operator": "<=", "value": 1},
            ]
        }
        def mock_resolver(p, field):
            return 65 if field == "age" else 3
        with patch("trialpilot.views.get_patient_value", side_effect=mock_resolver):
            result = evaluate_condition(patient, logic)
        self.assertTrue(result["result"])
 
    def test_missing_patient_value_returns_false(self):
        patient = self._make_patient()
        logic = {"field": "age", "operator": ">=", "value": 18}
        with patch("trialpilot.views.get_patient_value", return_value=None):
            result = evaluate_condition(patient, logic)
        self.assertFalse(result["result"])
 
 
class ExtractLabParametersTest(TestCase):
 
    def test_extracts_hemoglobin(self):
        analysis_json = {
            "eritrocitos": {
                "hemoglobina": {"value": 13.5, "unit": "g/dL"}
            }
        }
        results = extract_lab_parameters(analysis_json)
        names = [r["name"] for r in results]
        self.assertIn("hemoglobina", names)
 
    def test_empty_json_returns_empty(self):
        self.assertEqual(extract_lab_parameters({}), [])
 
    def test_none_returns_empty(self):
        self.assertEqual(extract_lab_parameters(None), [])
 
    def test_extracts_leucocitos(self):
        analysis_json = {
            "hematology": {
                "leucocitos": {"value": 8.0, "unit": "x10^9/L"}
            }
        }
        results = extract_lab_parameters(analysis_json)
        names = [r["name"] for r in results]
        self.assertIn("leucocitos", names)
        
# View functions

class IndexViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    def test_index_returns_200(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
 
    def test_index_uses_correct_template(self):
        response = self.client.get(reverse("index"))
        self.assertTemplateUsed(response, "trialpilot/index.html")
 
    def test_index_context_has_stats(self):
        response = self.client.get(reverse("index"))
        for key in ["n_diaries", "n_patients", "n_trials"]:
            self.assertIn(key, response.context)
            
class DiaryListViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
        self.diary = make_document()
 
    def test_diary_list_returns_200(self):
        response = self.client.get(reverse("diary_list"))
        self.assertEqual(response.status_code, 200)
 
    def test_diary_list_template(self):
        response = self.client.get(reverse("diary_list"))
        self.assertTemplateUsed(response, "trialpilot/diary_list.html")
 
    def test_diary_list_search_filter(self):
        response = self.client.get(reverse("diary_list") + "?search=diary")
        self.assertEqual(response.status_code, 200)
 
    def test_diary_list_status_extracted_filter(self):
        response = self.client.get(reverse("diary_list") + "?status=extracted")
        self.assertEqual(response.status_code, 200)
 
    def test_diary_list_status_not_extracted_filter(self):
        response = self.client.get(reverse("diary_list") + "?status=not_extracted")
        self.assertEqual(response.status_code, 200)
        
class TrialListViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
        self.trial_doc = make_clinical_trial_document()
 
    def test_trial_list_returns_200(self):
        response = self.client.get(reverse("trial_list"))
        self.assertEqual(response.status_code, 200)
 
    def test_trial_list_template(self):
        response = self.client.get(reverse("trial_list"))
        self.assertTemplateUsed(response, "trialpilot/trial_list.html")
 
    def test_trial_list_search_filter(self):
        response = self.client.get(reverse("trial_list") + "?search=Study")
        self.assertEqual(response.status_code, 200)
 
    def test_trial_list_pathology_filter(self):
        response = self.client.get(reverse("trial_list") + "?pathology_group=mama")
        self.assertEqual(response.status_code, 200)
 
    def test_trial_list_status_filter(self):
        response = self.client.get(reverse("trial_list") + "?trial_status=recruiting")
        self.assertEqual(response.status_code, 200)
        
class PatientListViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
        doc = make_document()
        self.patient = make_patient(doc)
 
    def test_patient_list_returns_200(self):
        response = self.client.get(reverse("patient_list"))
        self.assertEqual(response.status_code, 200)
 
    def test_patient_list_template(self):
        response = self.client.get(reverse("patient_list"))
        self.assertTemplateUsed(response, "trialpilot/patient_list.html")
 
    def test_patient_list_search_filter(self):
        response = self.client.get(reverse("patient_list") + "?search=NSCLC")
        self.assertEqual(response.status_code, 200)
 
    def test_patient_list_stage_filter(self):
        response = self.client.get(reverse("patient_list") + "?stage=IV")
        self.assertEqual(response.status_code, 200)
 

class DiaryDetailsViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    def test_nonexistent_diary_shows_error(self):
        response = self.client.get(reverse("diary_details", args=[9999]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
 
    @patch("trialpilot.views.extract_document_text", return_value="Sample diary content")
    def test_existing_diary_returns_200(self, mock_extract):
        doc = make_document()
        response = self.client.get(reverse("diary_details", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
 
    @patch("trialpilot.views.extract_document_text", return_value="Sample content")
    def test_wrong_type_shows_error(self, mock_extract):
        # A clinical trial document accessed via diary_details
        doc = make_clinical_trial_document()
        response = self.client.get(reverse("diary_details", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
        
class TrialDetailsViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    def test_nonexistent_trial_shows_error(self):
        response = self.client.get(reverse("trial_details", args=[9999]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)
 
    @patch("trialpilot.views.extract_document_text", return_value="Sample trial content")
    def test_existing_trial_returns_200(self, mock_extract):
        doc = make_clinical_trial_document()
        response = self.client.get(reverse("trial_details", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        
class DiaryRemoveViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    @patch("os.path.exists", return_value=False)
    def test_delete_existing_diary(self, mock_exists):
        doc = make_document()
        doc_id = doc.id
        payload = json.dumps({"diaries": [doc_id]})
        response = self.client.post(
            reverse("diary_remove"),
            data=payload,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertFalse(Document.objects.filter(id=doc_id).exists())
        
    def test_delete_existing_diary_removes_versions(self):
        doc = make_document()

        version = Version.objects.create(
            document=doc,
            version_name="RAW",
            file_path=ContentFile(
                b"dummy content",
                name="raw_test.txt"
            )
        )

        version_id = version.id

        response = self.client.post(
            reverse("diary_remove"),
            data=json.dumps({"diaries": [doc.id]}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            Version.objects.filter(id=version_id).exists()
        )

    def test_delete_existing_diary_removes_files(self):

        with TemporaryDirectory() as tmp:

            with override_settings(MEDIA_ROOT=tmp):

                doc = make_document()
                
                default_storage._wrapped = FileSystemStorage()
                
                saved_path = default_storage.save(
                    "documents/test_file.txt",
                    ContentFile(b"hello")
                )

                Version.objects.create(
                    document=doc,
                    version_name="RAW_test_file.txt",
                    file_path=saved_path
                )

                file_path = os.path.join(
                    tmp,
                    saved_path
                )

                self.assertTrue(
                    os.path.exists(file_path)
                )


                self.client.post(
                    reverse("diary_remove"),
                    data=json.dumps({
                        "diaries": [doc.id]
                    }),
                    content_type="application/json"
                )


                self.assertFalse(
                    os.path.exists(file_path)
                )
        
class TrialRemoveViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    @patch("os.path.exists", return_value=False)
    def test_delete_existing_trial(self, mock_exists):
        doc = make_clinical_trial_document()
        doc_id = doc.id
        payload = json.dumps({"trials": [doc_id]})
        response = self.client.post(
            reverse("trial_remove"),
            data=payload,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertFalse(Document.objects.filter(id=doc_id).exists())
    
    def test_delete_existing_trial_removes_files(self):

        with TemporaryDirectory() as tmp:
            
            with override_settings(MEDIA_ROOT=tmp):

                doc = make_clinical_trial_document()

                default_storage._wrapped = FileSystemStorage()
                
                saved_path = default_storage.save(
                    "documents/trial_file.txt",
                    ContentFile(b"trial content")
                )

                Version.objects.create(
                    document=doc,
                    version_name="RAW_trial_file.txt",
                    file_path=saved_path
                )


                file_path = default_storage.path(saved_path)

                self.assertTrue(
                    os.path.exists(file_path)
                )


                self.client.post(
                    reverse("trial_remove"),
                    data=json.dumps({
                        "trials": [doc.id]
                    }),
                    content_type="application/json"
                )


                self.assertFalse(
                    os.path.exists(file_path)
                )
    
    def test_delete_trial_removes_clinical_trial(self):

        doc = make_clinical_trial_document()

        trial_id = doc.clinical_trial.id


        self.client.post(
            reverse("trial_remove"),
            data=json.dumps({"trials":[doc.id]}),
            content_type="application/json"
        )


        self.assertFalse(
            ClinicalTrial.objects.filter(
                id=trial_id
            ).exists()
        )
    
    def test_delete_trial_removes_related_structures(self):

        doc = make_clinical_trial_document()

        cohort = Trial_cohort.objects.create(
            clinical_trial=doc.clinical_trial,
            cohort_id="1",
            name="Cohort A"
        )


        criterion = Trial_criteria.objects.create(
            document=doc,
            cohort=cohort,
            type="inclusion",
            raw_criterion="Age > 18"
        )


        logic = Logic_criteria.objects.create(
            criterion=criterion,
            raw_logic={"field":"age"}
        )


        self.client.post(
            reverse("trial_remove"),
            data=json.dumps({"trials":[doc.id]}),
            content_type="application/json"
        )


        self.assertFalse(
            Trial_cohort.objects.filter(id=cohort.id).exists()
        )

        self.assertFalse(
            Trial_criteria.objects.filter(id=criterion.id).exists()
        )

        self.assertFalse(
            Logic_criteria.objects.filter(id=logic.id).exists()
        )
        
        
    
        
class PatientResetViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    @patch("os.path.exists", return_value=False)
    def test_reset_existing_patient(self, mock_exists):
        doc = make_document()
        patient = make_patient(doc)
        patient_id = patient.id
        response = self.client.post(reverse("patient_reset", args=[patient_id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(Patient_profile.objects.filter(id=patient_id).exists())
        
        
    def test_reset_patient_removes_extracted_files(self):

        with TemporaryDirectory() as tmp:

            with override_settings(MEDIA_ROOT=tmp):

                doc = make_document()

                default_storage._wrapped = FileSystemStorage()
                
                patient = make_patient(doc)


                saved_path = default_storage.save(
                    "documents/parameters.json",
                    ContentFile(b"json content")
                )


                extracted_version = Version.objects.create(
                    document=doc,
                    version_name="EXTRACTED_parameters.json",
                    file_path=saved_path
                )


                file_path = default_storage.path(saved_path)


                self.assertTrue(
                    os.path.exists(file_path)
                )


                response = self.client.post(
                    reverse(
                        "patient_reset",
                        args=[patient.id]
                    )
                )


                self.assertEqual(
                    response.status_code,
                    200
                )


                self.assertFalse(
                    os.path.exists(file_path)
                )
                
    def test_reset_patient_removes_extracted_versions(self):

        doc = make_document()

        patient = make_patient(doc)


        raw_version = Version.objects.create(
            document=doc,
            version_name="RAW",
            file_path=ContentFile(
                b"raw",
                name="raw.txt"
            )
        )


        extracted_version = Version.objects.create(
            document=doc,
            version_name="EXTRACTED",
            file_path=ContentFile(
                b"json",
                name="params.json"
            )
        )


        self.client.post(
            reverse(
                "patient_reset",
                args=[patient.id]
            )
        )


        self.assertTrue(
            Version.objects.filter(
                id=raw_version.id
            ).exists()
        )


        self.assertFalse(
            Version.objects.filter(
                id=extracted_version.id
            ).exists()
        )
        
    def test_reset_patient_marks_document_as_not_extracted(self):

        doc = make_document()

        doc.extracted=True
        doc.save()


        patient = make_patient(doc)


        self.client.post(
            reverse(
                "patient_reset",
                args=[patient.id]
            )
        )


        doc.refresh_from_db()


        self.assertFalse(
            doc.extracted
        )
        
class DocumentUploadViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    def test_get_shows_form(self):
        response = self.client.get(reverse("document_upload"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
 
    @patch("trialpilot.views.document_save")
    def test_post_valid_file_redirects(self, mock_save):
        response = self.client.post(
            reverse("document_upload"),
            data={"file": make_txt_file(), "type": False},
        )
        self.assertEqual(response.status_code, 302)
 
    def test_post_invalid_extension_stays(self):
        bad = SimpleUploadedFile("data.csv", b"col1,col2", content_type="text/csv")
        response = self.client.post(
            reverse("document_upload"),
            data={"file": bad, "type": False},
        )
        self.assertEqual(response.status_code, 200)
        
class ClinicalTrialUploadViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    @patch("trialpilot.views.document_save")
    def test_post_valid_trial_redirects(self, mock_save):
        response = self.client.post(
            reverse("clinical_trial_upload"),
            data={
                "file": make_pdf_file(),
                "type": False,
                "study_name": "Test Trial",
                "pathology_group": "mama",
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "status": "recruiting",
            }
        )
        self.assertEqual(response.status_code, 302)
 
    def test_post_invalid_returns_400(self):
        response = self.client.post(
            reverse("clinical_trial_upload"),
            data={
                "file": make_pdf_file(),
                # missing study_name, pathology_group, dates, status
            }
        )
        self.assertEqual(response.status_code, 400)
        
class DevToolsViewTest(TestCase):
 
    def setUp(self):
        self.client = Client()
 
    def test_dev_tools_returns_200(self):
        response = self.client.get(reverse("dev_tools"))
        self.assertEqual(response.status_code, 200)
 
    def test_dev_tools_template(self):
        response = self.client.get(reverse("dev_tools"))
        self.assertTemplateUsed(response, "trialpilot/dev_tools.html")
 
    def test_dev_tools_context_keys(self):
        response = self.client.get(reverse("dev_tools"))
        for key in ["n_diaries", "n_trials", "n_patients", "total_matches"]:
            self.assertIn(key, response.context)