"""Tests du pipeline de notation IA."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from notation.models import NoteIA
from notation.pipeline import _sauver_notes, calculer_note_globale, noter_passage
from sessions_app.models import CritereNotation


# ============================================================================
# Helpers
# ============================================================================

def _make_ia_response(criteres_noms: list[str], note_val: float = 14.0) -> dict:
    return {
        'notes': [
            {'critere': nom, 'note': note_val, 'commentaire': f'Commentaire pour {nom}.'}
            for nom in criteres_noms
        ],
        'synthese': 'Bonne prestation globale.',
        'ton_detecte': 'assuré',
        '_personnalite_utilisee': 'neutre',
    }


# ============================================================================
# noter_passage — mode individuelle
# ============================================================================

@pytest.mark.django_db
class TestNoterPassageIndividuelle:

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_individuelle_creates_notes_for_each_student(
        self, mock_noter, passage_groupe, etudiant_user, etudiant_user2, session_obj
    ):
        criteres_noms = [c.nom for c in session_obj.criteres.all()]
        mock_noter.return_value = _make_ia_response(criteres_noms, note_val=15.0)
        session_obj.mode_notation_groupe = 'individuelle'
        session_obj.save()

        resultats = noter_passage(passage_groupe)

        assert 'erreurs' in resultats
        assert len(resultats['erreurs']) == 0
        # Un appel par étudiant
        assert mock_noter.call_count == 2

        for etu in [etudiant_user, etudiant_user2]:
            notes = NoteIA.objects.filter(passage=passage_groupe, etudiant=etu)
            assert notes.count() == len(criteres_noms)

        passage_groupe.refresh_from_db()
        assert passage_groupe.statut == 'note'

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_individuelle_no_students_returns_error(self, mock_noter, session_obj, db):
        from sessions_app.models import PassageEtudiant
        p = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=99,
        )
        resultats = noter_passage(p)
        assert 'erreur' in resultats
        mock_noter.assert_not_called()


# ============================================================================
# noter_passage — mode identique
# ============================================================================

@pytest.mark.django_db
class TestNoterPassageIdentique:

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_identique_calls_api_once_for_group(
        self, mock_noter, passage_groupe, etudiant_user, etudiant_user2, session_identique
    ):
        # Rattache le passage à la session identique
        passage_groupe.session = session_identique
        passage_groupe.save()
        criteres_noms = [c.nom for c in session_identique.criteres.all()]
        mock_noter.return_value = _make_ia_response(criteres_noms)

        noter_passage(passage_groupe)
        # Un seul appel pour tout le groupe
        assert mock_noter.call_count == 1

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_identique_copies_notes_to_all_students(
        self, mock_noter, passage_groupe, etudiant_user, etudiant_user2, session_identique
    ):
        passage_groupe.session = session_identique
        passage_groupe.save()
        criteres_noms = [c.nom for c in session_identique.criteres.all()]
        mock_noter.return_value = _make_ia_response(criteres_noms, note_val=16.0)

        noter_passage(passage_groupe)

        for etu in [etudiant_user, etudiant_user2]:
            note = NoteIA.objects.get(passage=passage_groupe, etudiant=etu)
            assert note.note_ia == 16.0

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_identique_error_response_propagated(self, mock_noter, passage_groupe, session_identique):
        passage_groupe.session = session_identique
        passage_groupe.save()
        mock_noter.return_value = {'erreur': 'API non disponible'}

        resultats = noter_passage(passage_groupe)
        assert len(resultats['erreurs']) > 0


# ============================================================================
# noter_passage — durée réelle calculée
# ============================================================================

@pytest.mark.django_db
class TestNoterPassageDureeReelle:

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_duree_reelle_calculated_from_dates(
        self, mock_noter, passage_obj, etudiant_user, session_obj
    ):
        now = timezone.now()
        passage_obj.date_debut = now
        passage_obj.date_fin = now + timedelta(minutes=14)
        passage_obj.save()

        criteres_noms = [c.nom for c in session_obj.criteres.all()]
        mock_noter.return_value = _make_ia_response(criteres_noms)

        noter_passage(passage_obj)

        # Vérifie que l'orchestrateur a reçu un contexte avec une durée réelle
        call_args = mock_noter.call_args
        ctx = call_args[0][0]  # premier argument positionnel
        assert ctx.duree_reelle_min > 0

    @patch('notation.pipeline.Orchestrateur.noter')
    def test_duree_reelle_zero_without_dates(self, mock_noter, passage_obj, session_obj):
        passage_obj.date_debut = None
        passage_obj.date_fin = None
        passage_obj.save()
        criteres_noms = [c.nom for c in session_obj.criteres.all()]
        mock_noter.return_value = _make_ia_response(criteres_noms)

        noter_passage(passage_obj)

        ctx = mock_noter.call_args[0][0]
        assert ctx.duree_reelle_min == 0.0


# ============================================================================
# _sauver_notes
# ============================================================================

@pytest.mark.django_db
class TestSauverNotes:

    def test_creates_note_ia_for_each_critere(self, passage_obj, etudiant_user, session_obj):
        criteres = list(session_obj.criteres.all())
        reponse = _make_ia_response([c.nom for c in criteres], note_val=13.0)
        _sauver_notes(passage_obj, etudiant_user, criteres, reponse)
        assert NoteIA.objects.filter(passage=passage_obj, etudiant=etudiant_user).count() == len(criteres)

    def test_note_value_stored_correctly(self, passage_obj, etudiant_user, session_obj):
        criteres = list(session_obj.criteres.all())
        reponse = _make_ia_response([c.nom for c in criteres], note_val=17.5)
        _sauver_notes(passage_obj, etudiant_user, criteres, reponse)
        notes = NoteIA.objects.filter(passage=passage_obj, etudiant=etudiant_user)
        for note in notes:
            assert note.note_ia == 17.5
            assert note.note_finale == 17.5
            assert note.modifiee_par_prof is False

    def test_update_or_create_on_duplicate(self, passage_obj, etudiant_user, session_obj):
        criteres = list(session_obj.criteres.all())
        reponse1 = _make_ia_response([c.nom for c in criteres], note_val=10.0)
        reponse2 = _make_ia_response([c.nom for c in criteres], note_val=18.0)
        _sauver_notes(passage_obj, etudiant_user, criteres, reponse1)
        _sauver_notes(passage_obj, etudiant_user, criteres, reponse2)
        notes = NoteIA.objects.filter(passage=passage_obj, etudiant=etudiant_user)
        assert notes.count() == len(criteres)  # pas de doublons
        for note in notes:
            assert note.note_ia == 18.0  # mise à jour

    def test_missing_critere_in_response_uses_default_10(self, passage_obj, etudiant_user, session_obj):
        criteres = list(session_obj.criteres.all())
        reponse = {'notes': [], 'synthese': '', 'ton_detecte': ''}  # pas de notes
        _sauver_notes(passage_obj, etudiant_user, criteres, reponse)
        notes = NoteIA.objects.filter(passage=passage_obj, etudiant=etudiant_user)
        for note in notes:
            assert note.note_ia == 10.0  # valeur par défaut


# ============================================================================
# calculer_note_globale
# ============================================================================

@pytest.mark.django_db
class TestCalculerNoteGlobale:

    def test_weighted_average(self, passage_obj, etudiant_user, session_obj):
        criteres = list(session_obj.criteres.all())
        # Clarté: coef=1.0, Structure: coef=2.0
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user,
            critere=criteres[0], note_ia=12.0, note_finale=12.0,
        )
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user,
            critere=criteres[1], note_ia=18.0, note_finale=18.0,
        )
        # (12*1 + 18*2) / (1+2) = (12+36)/3 = 48/3 = 16.0
        result = calculer_note_globale(passage_obj, etudiant_user)
        assert result == pytest.approx(16.0, rel=1e-3)

    def test_returns_none_when_no_notes(self, passage_obj, etudiant_user):
        result = calculer_note_globale(passage_obj, etudiant_user)
        assert result is None

    def test_uses_note_finale_not_note_ia(self, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user,
            critere=critere, note_ia=10.0, note_finale=20.0,  # prof a modifié
        )
        result = calculer_note_globale(passage_obj, etudiant_user)
        assert result == pytest.approx(20.0, rel=1e-3)

    def test_single_note_returns_that_note(self, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user,
            critere=critere, note_ia=14.5, note_finale=14.5,
        )
        result = calculer_note_globale(passage_obj, etudiant_user)
        assert result == pytest.approx(14.5, rel=1e-3)
