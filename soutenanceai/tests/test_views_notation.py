"""Tests des vues de notation : consultation, modification de notes, rapport PDF."""
import json
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from notation.models import NoteIA
from sessions_app.models import PassageEtudiant, Session


# ============================================================================
# notes_passage
# ============================================================================

@pytest.mark.django_db
class TestNotesPassage:

    def test_prof_can_view_notes(self, client_prof, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user,
            critere=critere, note_ia=14.0, note_finale=14.0,
        )
        url = reverse('notation:notes_passage', args=[passage_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert 'notes_par_etudiant' in resp.context

    def test_notes_include_global_average(self, client_prof, passage_obj, etudiant_user, session_obj):
        for c in session_obj.criteres.all():
            NoteIA.objects.create(
                passage=passage_obj, etudiant=etudiant_user,
                critere=c, note_ia=16.0, note_finale=16.0,
            )
        url = reverse('notation:notes_passage', args=[passage_obj.pk])
        resp = client_prof.get(url)
        notes_data = resp.context['notes_par_etudiant']
        assert any(d['globale'] is not None for d in notes_data)

    def test_other_prof_cannot_view_notes(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Autre', langue='fr', duree_presentation=10,
        )
        p2 = PassageEtudiant.objects.create(
            session=s2, heure_prevue=timezone.now(), ordre_passage=1,
        )
        url = reverse('notation:notes_passage', args=[p2.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 404

    def test_etudiant_denied(self, client_etudiant, passage_obj):
        url = reverse('notation:notes_passage', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 403

    def test_anonymous_redirected(self, client, passage_obj):
        url = reverse('notation:notes_passage', args=[passage_obj.pk])
        resp = client.get(url)
        assert resp.status_code == 302


# ============================================================================
# modifier_note
# ============================================================================

@pytest.mark.django_db
class TestModifierNote:

    def _create_note(self, passage_obj, etudiant_user, session_obj, value=12.0):
        critere = session_obj.criteres.first()
        return NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user,
            critere=critere, note_ia=value, note_finale=value,
        )

    def test_prof_can_modify_note(self, client_prof, passage_obj, etudiant_user, session_obj):
        note = self._create_note(passage_obj, etudiant_user, session_obj)
        url = reverse('notation:modifier_note', args=[note.pk])
        resp = client_prof.post(url, {'note_finale': '18.0', 'commentaire_prof': 'Excellent.'})
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['ok'] is True
        assert data['note_finale'] == 18.0
        note.refresh_from_db()
        assert note.note_finale == 18.0
        assert note.modifiee_par_prof is True
        assert note.commentaire_prof == 'Excellent.'

    def test_note_clamped_to_0_20(self, client_prof, passage_obj, etudiant_user, session_obj):
        note = self._create_note(passage_obj, etudiant_user, session_obj)
        url = reverse('notation:modifier_note', args=[note.pk])
        # Tentative de mettre 25/20
        client_prof.post(url, {'note_finale': '25.0'})
        note.refresh_from_db()
        assert note.note_finale == 20.0

    def test_note_clamped_below_0(self, client_prof, passage_obj, etudiant_user, session_obj):
        note = self._create_note(passage_obj, etudiant_user, session_obj)
        url = reverse('notation:modifier_note', args=[note.pk])
        client_prof.post(url, {'note_finale': '-5.0'})
        note.refresh_from_db()
        assert note.note_finale == 0.0

    def test_invalid_note_returns_400(self, client_prof, passage_obj, etudiant_user, session_obj):
        note = self._create_note(passage_obj, etudiant_user, session_obj)
        url = reverse('notation:modifier_note', args=[note.pk])
        resp = client_prof.post(url, {'note_finale': 'pas_un_nombre'})
        assert resp.status_code == 400
        data = json.loads(resp.content)
        assert data['ok'] is False

    def test_other_prof_cannot_modify(self, client_prof, prof_user2, db, passage_obj, etudiant_user, session_obj):
        from accounts.models import User
        note = self._create_note(passage_obj, etudiant_user, session_obj)
        # Prof2 tente de modifier la note
        client_prof2 = MagicMock()  # on n'a pas de fixture client_prof2 direct
        from django.test import Client
        c = Client()
        c.force_login(prof_user2)
        url = reverse('notation:modifier_note', args=[note.pk])
        resp = c.post(url, {'note_finale': '20.0'})
        assert resp.status_code == 404

    def test_get_method_not_allowed(self, client_prof, passage_obj, etudiant_user, session_obj):
        note = self._create_note(passage_obj, etudiant_user, session_obj)
        url = reverse('notation:modifier_note', args=[note.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 405


# ============================================================================
# declencher_notation
# ============================================================================

@pytest.mark.django_db
class TestDeclencherNotation:

    @patch('notation.views.noter_passage', return_value={'notes_par_etudiant': {}, 'erreurs': []})
    def test_prof_can_trigger_notation(self, mock_noter, client_prof, passage_obj):
        url = reverse('notation:declencher', args=[passage_obj.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 302
        mock_noter.assert_called_once_with(passage_obj)

    @patch('notation.views.noter_passage', return_value={'erreurs': ['Erreur API']})
    def test_errors_in_notation_shows_warning(self, mock_noter, client_prof, passage_obj):
        url = reverse('notation:declencher', args=[passage_obj.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 302
        # Le message de warning doit être dans la session
        messages = list(resp.wsgi_request._messages)
        assert any('artielle' in str(m) or 'rreur' in str(m) for m in messages)

    def test_other_prof_cannot_trigger(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='A', langue='fr', duree_presentation=10,
        )
        p2 = PassageEtudiant.objects.create(
            session=s2, heure_prevue=timezone.now(), ordre_passage=1,
        )
        url = reverse('notation:declencher', args=[p2.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 404

    def test_get_method_not_allowed(self, client_prof, passage_obj):
        url = reverse('notation:declencher', args=[passage_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 405


# ============================================================================
# telecharger_rapport
# ============================================================================

@pytest.mark.django_db
class TestTelechargerRapport:

    @patch('notation.views.generer_rapport_pdf', return_value=b'%PDF-1.4 fake pdf content')
    def test_returns_pdf_response(self, mock_pdf, client_prof, passage_obj):
        url = reverse('notation:rapport_pdf', args=[passage_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/pdf'
        assert 'attachment' in resp['Content-Disposition']
        assert str(passage_obj.pk) in resp['Content-Disposition']

    @patch('notation.views.generer_rapport_pdf', return_value=b'%PDF')
    def test_other_prof_cannot_download(self, mock_pdf, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='B', langue='fr', duree_presentation=10,
        )
        p2 = PassageEtudiant.objects.create(
            session=s2, heure_prevue=timezone.now(), ordre_passage=1,
        )
        url = reverse('notation:rapport_pdf', args=[p2.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 404

    def test_etudiant_cannot_download(self, client_etudiant, passage_obj):
        url = reverse('notation:rapport_pdf', args=[passage_obj.pk])
        resp = client_etudiant.get(url)
        assert resp.status_code == 403


# ============================================================================
# Import local (évite circular import)
# ============================================================================
try:
    from unittest.mock import MagicMock
except ImportError:
    pass
