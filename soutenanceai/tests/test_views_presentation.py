"""Tests des vues côté étudiant : dashboard, upload, salle, AJAX."""
import json
from unittest.mock import patch, MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from sessions_app.models import PassageEtudiant, Session


# ============================================================================
# Dashboard étudiant
# ============================================================================

@pytest.mark.django_db
class TestDashboardEtudiant:

    def test_etudiant_sees_own_passages(self, client_etudiant, passage_obj):
        url = reverse('presentation:dashboard_etudiant')
        resp = client_etudiant.get(url)
        assert resp.status_code == 200
        assert passage_obj in resp.context['passages']

    def test_anonymous_redirected_to_login(self, client):
        url = reverse('presentation:dashboard_etudiant')
        resp = client.get(url)
        assert resp.status_code == 302
        assert 'login' in resp['Location']

    def test_professeur_denied(self, client_prof):
        url = reverse('presentation:dashboard_etudiant')
        resp = client_prof.get(url)
        assert resp.status_code == 403

    def test_etudiant_does_not_see_others_passages(self, client_etudiant, db, prof_user, session_obj):
        from accounts.models import User
        autre = User.objects.create_user(username='autre', password='pass', role='etudiant')
        p_autre = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=99,
        )
        p_autre.etudiants.add(autre)
        url = reverse('presentation:dashboard_etudiant')
        resp = client_etudiant.get(url)
        assert p_autre not in resp.context['passages']


# ============================================================================
# Détail passage
# ============================================================================

@pytest.mark.django_db
class TestDetailPassage:

    def test_etudiant_sees_own_passage(self, client_etudiant, passage_obj):
        url = reverse('presentation:detail_passage', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 200
        assert resp.context['passage'] == passage_obj

    def test_etudiant_cannot_see_others_passage(self, client_etudiant, db, prof_user, session_obj):
        from accounts.models import User
        autre = User.objects.create_user(username='autre2', password='pass', role='etudiant')
        p2 = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=88,
        )
        p2.etudiants.add(autre)
        url = reverse('presentation:detail_passage', args=[p2.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 403


# ============================================================================
# Upload fichiers
# ============================================================================

@pytest.mark.django_db
class TestUploadFichiers:

    def test_get_upload_form(self, client_etudiant, passage_obj):
        url = reverse('presentation:upload', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 200
        assert 'form' in resp.context

    @patch('presentation.views.convertir_pptx_en_pdf', return_value=None)
    def test_upload_pptx_redirects_to_salle(self, mock_convert, client_etudiant, passage_obj):
        url = reverse('presentation:upload', args=[passage_obj.pk])
        fake_pptx = SimpleUploadedFile(
            'presentation.pptx',
            b'PK\x03\x04fake_pptx_content',
            content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        )
        resp = client_etudiant.post(url, {'fichier_pptx': fake_pptx})
        assert resp.status_code == 302
        assert 'salle' in resp['Location']

    @patch('presentation.views.convertir_pptx_en_pdf', return_value=None)
    def test_upload_calls_libreoffice_conversion(self, mock_convert, client_etudiant, passage_obj):
        url = reverse('presentation:upload', args=[passage_obj.pk])
        fake_pptx = SimpleUploadedFile(
            'pres.pptx', b'fake', content_type='application/octet-stream',
        )
        client_etudiant.post(url, {'fichier_pptx': fake_pptx})
        mock_convert.assert_called_once()

    def test_cannot_upload_to_others_passage(self, client_etudiant, db, prof_user, session_obj):
        from accounts.models import User
        autre = User.objects.create_user(username='autre3', password='pass', role='etudiant')
        p2 = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=77,
        )
        p2.etudiants.add(autre)
        url = reverse('presentation:upload', args=[p2.pk])
        resp = client_etudiant.post(url, {})
        assert resp.status_code == 403


# ============================================================================
# Salle de présentation
# ============================================================================

@pytest.mark.django_db
class TestSallePresentation:

    def test_redirects_if_no_pptx(self, client_etudiant, passage_obj):
        url = reverse('presentation:salle', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 302
        assert 'upload' in resp['Location']

    def test_redirects_if_rapport_required_but_missing(self, client_etudiant, passage_obj, session_obj):
        session_obj.rapport_obligatoire = True
        session_obj.save()
        # Ajoute un PPTX fictif mais pas de rapport
        passage_obj.fichier_pptx = SimpleUploadedFile('p.pptx', b'data')
        passage_obj.save()
        url = reverse('presentation:salle', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 302
        assert 'upload' in resp['Location']
        # Cleanup
        session_obj.rapport_obligatoire = False
        session_obj.save()

    @patch('presentation.views.Path')
    def test_salle_renders_with_pptx(self, mock_path, client_etudiant, passage_obj):
        """Salle se charge si PPTX présent (pdf_url peut être vide si pas encore converti)."""
        passage_obj.fichier_pptx = SimpleUploadedFile('slide.pptx', b'data')
        passage_obj.save()
        # Mock le dossier PDF pour qu'il n'existe pas (pdf_url = '')
        mock_instance = MagicMock()
        mock_instance.__truediv__ = lambda self, x: mock_instance
        mock_instance.exists.return_value = False
        mock_path.return_value = mock_instance

        url = reverse('presentation:salle', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 200
        assert 'passage' in resp.context

    def test_cannot_access_others_salle(self, client_etudiant, db, prof_user, session_obj):
        from accounts.models import User
        autre = User.objects.create_user(username='autre4', password='pass', role='etudiant')
        p2 = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=66,
        )
        p2.etudiants.add(autre)
        url = reverse('presentation:salle', args=[p2.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 403


# ============================================================================
# AJAX — Démarrer
# ============================================================================

@pytest.mark.django_db
class TestApiDemarrer:

    def test_demarrer_sets_en_cours(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_demarrer', args=[passage_obj.pk])
        resp = client_etudiant.post(url)
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True
        passage_obj.refresh_from_db()
        assert passage_obj.statut == 'en_cours'
        assert passage_obj.date_debut is not None

    def test_demarrer_get_not_allowed(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_demarrer', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 405

    def test_demarrer_only_for_own_passage(self, client_etudiant, db, prof_user, session_obj):
        from accounts.models import User
        autre = User.objects.create_user(username='autre5', password='pass', role='etudiant')
        p2 = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=55,
        )
        p2.etudiants.add(autre)
        url = reverse('presentation:api_demarrer', args=[p2.pk])
        resp = client_etudiant.post(url)
        assert resp.status_code == 403


# ============================================================================
# AJAX — Terminer présentation (génère les questions IA)
# ============================================================================

@pytest.mark.django_db
class TestApiTerminerPresentation:

    @patch('presentation.views.generer_questions', return_value=['Q1 ?', 'Q2 ?', 'Q3 ?'])
    def test_terminer_presentation_avec_questions(self, mock_gen, client_etudiant, passage_obj, settings):
        settings.ANTHROPIC_API_KEY = 'fake-key'
        url = reverse('presentation:api_terminer_presentation', args=[passage_obj.pk])
        resp = client_etudiant.post(url)
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True
        assert len(data['questions']) == 3
        passage_obj.refresh_from_db()
        assert passage_obj.statut == 'questions'

    @patch('presentation.views.generer_questions')
    def test_terminer_sans_cle_api_ne_genere_pas(self, mock_gen, client_etudiant, passage_obj, settings):
        settings.ANTHROPIC_API_KEY = ''
        url = reverse('presentation:api_terminer_presentation', args=[passage_obj.pk])
        resp = client_etudiant.post(url)
        assert resp.status_code == 200
        mock_gen.assert_not_called()

    @patch('presentation.views.generer_questions', side_effect=Exception('API error'))
    def test_exception_in_question_generation_handled(self, mock_gen, client_etudiant, passage_obj, settings):
        settings.ANTHROPIC_API_KEY = 'fake-key'
        url = reverse('presentation:api_terminer_presentation', args=[passage_obj.pk])
        resp = client_etudiant.post(url)
        # L'exception ne doit pas faire crasher la vue
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True


# ============================================================================
# AJAX — Terminer passage (lance la notation)
# ============================================================================

@pytest.mark.django_db
class TestApiTerminerPassage:

    @patch('presentation.views.noter_passage')
    def test_terminer_passage_avec_cle(self, mock_noter, client_etudiant, passage_obj, settings):
        settings.ANTHROPIC_API_KEY = 'fake-key'
        url = reverse('presentation:api_terminer_passage', args=[passage_obj.pk])
        resp = client_etudiant.post(url)
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True
        mock_noter.assert_called_once_with(passage_obj)
        passage_obj.refresh_from_db()
        assert passage_obj.statut == 'termine'
        assert passage_obj.date_fin is not None

    @patch('presentation.views.noter_passage')
    def test_terminer_sans_cle_ne_lance_pas_pipeline(self, mock_noter, client_etudiant, passage_obj, settings):
        settings.ANTHROPIC_API_KEY = ''
        url = reverse('presentation:api_terminer_passage', args=[passage_obj.pk])
        client_etudiant.post(url)
        mock_noter.assert_not_called()


# ============================================================================
# AJAX — Upload vidéo
# ============================================================================

@pytest.mark.django_db
class TestApiVideo:

    def test_upload_video_without_file_returns_400(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_video', args=[passage_obj.pk])
        resp = client_etudiant.post(url)
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert data['ok'] is False

    def test_upload_video_with_file_returns_200(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_video', args=[passage_obj.pk])
        fake_video = SimpleUploadedFile('video.webm', b'fake_video_data', content_type='video/webm')
        resp = client_etudiant.post(url, {'video': fake_video})
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True


# ============================================================================
# AJAX — Upload posture
# ============================================================================

@pytest.mark.django_db
class TestApiPosture:

    def test_upload_posture_valid_json(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_posture', args=[passage_obj.pk])
        payload = {
            'mesures': [
                {'timestamp': 1.0, 'looking_at_camera': True, 'head_tilt': 2.0},
                {'timestamp': 2.0, 'looking_at_camera': False, 'head_tilt': -1.5},
            ]
        }
        resp = client_etudiant.post(
            url, json.dumps(payload), content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True
        passage_obj.refresh_from_db()
        assert len(passage_obj.donnees_posture['serie']) == 2

    def test_upload_posture_accumulates_data(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_posture', args=[passage_obj.pk])
        for i in range(3):
            payload = {'mesures': [{'timestamp': float(i), 'looking_at_camera': True}]}
            client_etudiant.post(url, json.dumps(payload), content_type='application/json')
        passage_obj.refresh_from_db()
        assert len(passage_obj.donnees_posture['serie']) == 3

    def test_upload_posture_invalid_json_returns_400(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_posture', args=[passage_obj.pk])
        resp = client_etudiant.post(url, 'invalid json', content_type='application/json')
        assert resp.status_code == 400


# ============================================================================
# AJAX — Répondre à une question
# ============================================================================

@pytest.mark.django_db
class TestApiRepondre:

    @patch('notation.agents.evaluer_reponse', return_value={'note': 15.0, 'commentaire': 'Bonne réponse.'})
    def test_repondre_valide(self, mock_eval, client_etudiant, passage_obj, settings):
        settings.ANTHROPIC_API_KEY = 'fake-key'
        url = reverse('presentation:api_repondre', args=[passage_obj.pk])
        payload = {
            'question': 'Expliquez votre algorithme.',
            'reponse': 'J\'ai utilisé une approche récursive.',
        }
        resp = client_etudiant.post(
            url, json.dumps(payload), content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True
        assert data['evaluation']['note'] == 15.0

    def test_repondre_sans_question_retourne_400(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_repondre', args=[passage_obj.pk])
        payload = {'question': '', 'reponse': 'Réponse'}
        resp = client_etudiant.post(
            url, json.dumps(payload), content_type='application/json',
        )
        assert resp.status_code == 400

    def test_repondre_sans_reponse_retourne_400(self, client_etudiant, passage_obj):
        url = reverse('presentation:api_repondre', args=[passage_obj.pk])
        payload = {'question': 'Question ?', 'reponse': ''}
        resp = client_etudiant.post(
            url, json.dumps(payload), content_type='application/json',
        )
        assert resp.status_code == 400

    @patch('notation.agents.evaluer_reponse', return_value={'note': 12.0, 'commentaire': 'OK'})
    def test_repondre_cree_question_posee(self, mock_eval, client_etudiant, passage_obj, settings):
        from notation.models import QuestionPosee
        settings.ANTHROPIC_API_KEY = 'fake-key'
        url = reverse('presentation:api_repondre', args=[passage_obj.pk])
        payload = {'question': 'Quelle est votre méthode ?', 'reponse': 'Agile.'}
        client_etudiant.post(url, json.dumps(payload), content_type='application/json')
        assert QuestionPosee.objects.filter(passage=passage_obj).exists()
        q = QuestionPosee.objects.get(passage=passage_obj)
        assert q.question == 'Quelle est votre méthode ?'
        assert q.reponse_etudiant == 'Agile.'
