from django.test import TestCase
from trialpilot.models import *
from datetime import date
from django.db import IntegrityError

class DocumentModelTest(TestCase):

    def test_create_clinical_diary_document(self):

        document = Document.objects.create(
            title="Patient diary 001",
            type=Document.DocumentType.CLINICAL_DIARY
        )

        self.assertEqual(
            document.title,
            "Patient diary 001"
        )

        self.assertEqual(
            document.type,
            "diary"
        )

        self.assertFalse(
            document.extracted
        )


    def test_document_string_representation(self):

        document = Document.objects.create(
            title="Trial ABC",
            type=Document.DocumentType.CLINICAL_TRIAL
        )

        self.assertEqual(
            str(document),
            "Trial ABC - trial"
        )
        
class ClinicalTrialModelTest(TestCase):

    def test_create_clinical_trial(self):

        document = Document.objects.create(
            title="Trial document",
            type=Document.DocumentType.CLINICAL_TRIAL
        )


        trial = ClinicalTrial.objects.create(
            document=document,
            study_name="Lung Cancer Trial",
            pathology_group=
                ClinicalTrial.PathologyGroupType.PNEUMOLOGIA,
            status=
                ClinicalTrial.TrialStatus.RECRUITING
        )


        self.assertEqual(
            trial.study_name,
            "Lung Cancer Trial"
        )


        self.assertEqual(
            trial.status,
            "recruiting"
        )


    def test_trial_str(self):

        document = Document.objects.create(
            title="doc",
            type="trial"
        )

        trial = ClinicalTrial.objects.create(
            document=document,
            study_name="Trial X",
            pathology_group="mama",
            status="closed"
        )

        self.assertEqual(
            str(trial),
            "Trial X"
        )
        
class VersionModelTest(TestCase):

    def test_document_can_have_versions(self):

        document = Document.objects.create(
            title="Diary",
            type="diary"
        )


        version = Version.objects.create(
            document=document,
            version_name="v1"
        )


        self.assertEqual(
            document.versions.count(),
            1
        )


        self.assertEqual(
            str(version),
            "Diary - v1"
        )
        
class PatientProfileModelTest(TestCase):

    def test_create_patient_profile(self):

        document = Document.objects.create(
            title="Patient diary",
            type="diary"
        )


        patient = Patient_profile.objects.create(
            document=document,
            age=55,
            gender="male",
            diagnosis="Lung Cancer",
            stage="IV"
        )


        self.assertEqual(
            patient.age,
            55
        )


        self.assertEqual(
            patient.diagnosis,
            "Lung Cancer"
        )


    def test_patient_str(self):

        document = Document.objects.create(
            title="Diary",
            type="diary"
        )


        patient = Patient_profile.objects.create(
            document=document,
            diagnosis="Breast Cancer"
        )


        self.assertEqual(
            str(patient),
            f"Patient {patient.id} - Breast Cancer"
        )
        
class TreatmentModelTest(TestCase):

    def test_patient_treatment_relation(self):

        document = Document.objects.create(
            title="Diary",
            type="diary"
        )


        patient = Patient_profile.objects.create(
            document=document
        )


        treatment = Treatment.objects.create(
            patient=patient,
            treatment_name="Chemotherapy",
            start_date=date(2025,1,1)
        )


        self.assertEqual(
            patient.treatments.count(),
            1
        )


        self.assertIn(
            "Chemotherapy",
            str(treatment)
        )
        
class TrialCohortModelTest(TestCase):

    def test_create_cohort(self):

        document = Document.objects.create(
            title="Trial",
            type="trial"
        )


        trial = ClinicalTrial.objects.create(
            document=document,
            study_name="Study A",
            pathology_group="mama",
            status="recruiting"
        )


        cohort = Trial_cohort.objects.create(
            clinical_trial=trial,
            cohort_id="A",
            name="Advanced patients"
        )


        self.assertEqual(
            trial.cohorts.count(),
            1
        )


        self.assertEqual(
            str(cohort),
            "Study A - Advanced patients"
        )
        
class TrialCriteriaModelTest(TestCase):

    def test_create_trial_criterion(self):

        document = Document.objects.create(
            title="Trial",
            type="trial"
        )


        criterion = Trial_criteria.objects.create(
            document=document,
            type=Trial_criteria.CriterionType.INCLUSION,
            raw_criterion="Age > 18"
        )


        self.assertFalse(
            criterion.validated
        )


        self.assertEqual(
            criterion.type,
            "inclusion"
        )
        
class LogicCriteriaModelTest(TestCase):

    def test_logic_is_connected_to_criterion(self):

        document = Document.objects.create(
            title="Trial",
            type="trial"
        )


        criterion = Trial_criteria.objects.create(
            document=document,
            type="inclusion",
            raw_criterion="Age > 18"
        )


        logic = Logic_criteria.objects.create(
            criterion=criterion,
            raw_logic={
                "field":"age",
                "operator":">",
                "value":18
            }
        )


        self.assertEqual(
            criterion.logic,
            logic
        )


class PatientTrialMatchTest(TestCase):

    def test_duplicate_match_is_not_allowed(self):

        document = Document.objects.create(
            title="Diary",
            type="diary"
        )


        patient = Patient_profile.objects.create(
            document=document
        )


        trial_doc = Document.objects.create(
            title="Trial",
            type="trial"
        )


        Patient_trial_match.objects.create(
            patient=patient,
            trial=trial_doc,
            decision="eligible"
        )


        with self.assertRaises(IntegrityError):

            Patient_trial_match.objects.create(
                patient=patient,
                trial=trial_doc,
                decision="eligible"
            )

class CriterionEvaluationTest(TestCase):

    def test_unique_evaluation_per_match_and_criterion(self):

        document = Document.objects.create(
            title="Trial X",
            type=Document.DocumentType.CLINICAL_TRIAL
        )

        trial = ClinicalTrial.objects.create(
            document=document,
            study_name="Study ABC",
            pathology_group=ClinicalTrial.PathologyGroupType.MAMA,
            status=ClinicalTrial.TrialStatus.RECRUITING
        )

        criterion = Trial_criteria.objects.create(
            document=document,
            type=Trial_criteria.CriterionType.INCLUSION,
            raw_criterion="Age ≥ 18"
        )

        patient = Patient_profile.objects.create(
            document=document,
            age=55,
            gender=Patient_profile.GenderType.MALE
        )

        match = Patient_trial_match.objects.create(
            patient=patient,
            trial=document,
            decision=Patient_trial_match.Decision.ELIGIBLE
        )

        evaluation = Criterion_evaluation.objects.create(
            match=match,
            criterion=criterion,
            automatic_result="pass",
            evaluation_method="rule"
        )

        self.assertEqual(
            evaluation.automatic_result,
            "pass"
        )
        
    def test_duplicate_evaluation_not_allowed(self):

        document = Document.objects.create(
            title="Trial X",
            type=Document.DocumentType.CLINICAL_TRIAL
        )

        trial = ClinicalTrial.objects.create(
            document=document,
            study_name="Study ABC",
            pathology_group=ClinicalTrial.PathologyGroupType.MAMA,
            status=ClinicalTrial.TrialStatus.RECRUITING
        )

        criterion = Trial_criteria.objects.create(
            document=document,
            type=Trial_criteria.CriterionType.INCLUSION,
            raw_criterion="Age ≥ 18"
        )

        patient = Patient_profile.objects.create(
            document=document,
            age=55,
            gender=Patient_profile.GenderType.MALE
        )

        match = Patient_trial_match.objects.create(
            patient=patient,
            trial=document,
            decision=Patient_trial_match.Decision.ELIGIBLE
        )


        Criterion_evaluation.objects.create(
            match=match,
            criterion=criterion,
            automatic_result="pass",
            evaluation_method="rule"
        )

        with self.assertRaises(IntegrityError):
            Criterion_evaluation.objects.create(
                match=match,
                criterion=criterion,
                automatic_result="fail",
                evaluation_method="llm"
            )

