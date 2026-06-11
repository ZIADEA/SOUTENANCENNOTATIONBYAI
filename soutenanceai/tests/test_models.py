"""Tests des modèles : User, Session, CritereNotation, PassageEtudiant, NoteIA, QuestionPosee."""
import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import User
from notation.models import NoteIA, QuestionPosee
from sessions_app.models import CritereNotation, PassageEtudiant, Session


# ============================================================================
# Modèle User
# ============================================================================

@pytest.mark.django_db
class TestUserModel:

    def test_create_superadmin(self):
        u = User.objects.create_user(
            username='sa', password='pass123', role=User.ROLE_SUPERADMIN, is_superuser=True,
        )
        assert u.role == 'superadmin'
        assert u.is_superadmin is True
        assert u.is_professeur is False
        assert u.is_etudiant is False

    def test_create_professeur(self):
        u = User.objects.create_user(
            username='prof', password='pass123', role=User.ROLE_PROFESSEUR,
        )
        assert u.is_professeur is True
        assert u.is_superadmin is False
        assert u.is_etudiant is False

    def test_create_etudiant(self):
        u = User.objects.create_user(
            username='etu', password='pass123', role=User.ROLE_ETUDIANT,
        )
        assert u.is_etudiant is True
        assert u.is_professeur is False

    def test_is_superadmin_via_is_superuser(self):
        """Un is_superuser est considéré superadmin même si role=etudiant."""
        u = User.objects.create_user(
            username='su', password='pass', role=User.ROLE_ETUDIANT, is_superuser=True,
        )
        assert u.is_superadmin is True

    def test_default_role_is_etudiant(self):
        u = User.objects.create_user(username='default', password='pass')
        assert u.role == User.ROLE_ETUDIANT

    def test_str_with_full_name(self):
        u = User.objects.create_user(
            username='jdoe', password='pass', role=User.ROLE_PROFESSEUR,
            first_name='Jean', last_name='Doe',
        )
        assert 'Jean Doe' in str(u)
        assert 'Professeur' in str(u)

    def test_str_without_full_name(self):
        u = User.objects.create_user(
            username='noname', password='pass', role=User.ROLE_ETUDIANT,
        )
        assert 'noname' in str(u)

    def test_cree_par_relationship(self, prof_user, etudiant_user):
        assert etudiant_user.cree_par == prof_user
        assert etudiant_user in prof_user.comptes_crees.all()

    def test_cree_par_set_null_on_prof_delete(self, db):
        prof = User.objects.create_user(username='ptemp', password='pass', role='professeur')
        etu = User.objects.create_user(
            username='etemp', password='pass', role='etudiant', cree_par=prof,
        )
        prof.delete()
        etu.refresh_from_db()
        assert etu.cree_par is None

    def test_role_choices_are_complete(self):
        choices = dict(User.ROLE_CHOICES)
        assert 'superadmin' in choices
        assert 'professeur' in choices
        assert 'etudiant' in choices


# ============================================================================
# Modèle Session
# ============================================================================

@pytest.mark.django_db
class TestSessionModel:

    def test_create_session(self, prof_user):
        s = Session.objects.create(
            professeur=prof_user,
            titre='Test Session',
            langue='fr',
            duree_presentation=15,
        )
        assert s.pk is not None
        assert s.style_questionnement == 'mentor'  # valeur par défaut
        assert s.style_notation == 'juste'         # valeur par défaut
        assert s.mode_notation_groupe == 'individuelle'  # valeur par défaut
        assert s.rapport_obligatoire is False

    def test_str_session(self, session_obj):
        s = str(session_obj)
        assert 'Session Test ML' in s
        assert 'Français' in s

    def test_session_ordering_newest_first(self, db, prof_user):
        s1 = Session.objects.create(professeur=prof_user, titre='Ancienne', langue='fr', duree_presentation=10)
        s2 = Session.objects.create(professeur=prof_user, titre='Nouvelle', langue='fr', duree_presentation=10)
        sessions = list(Session.objects.filter(professeur=prof_user))
        assert sessions[0] == s2  # plus récente en premier

    def test_session_criteres_relation(self, session_obj):
        assert session_obj.criteres.count() == 2

    def test_session_langue_choices(self, prof_user):
        for code, _ in Session.LANGUE_CHOICES:
            s = Session.objects.create(
                professeur=prof_user, titre=f'Sess {code}', langue=code, duree_presentation=10,
            )
            assert s.langue == code
            s.delete()

    def test_session_personnalite_choices(self, prof_user):
        for code, _ in Session.PERSONNALITE_CHOICES:
            s = Session.objects.create(
                professeur=prof_user, titre=f'P{code}', langue='fr',
                duree_presentation=10, personnalite_ia=code,
            )
            assert s.personnalite_ia == code
            s.delete()

    def test_cascade_delete_with_criteres(self, db, prof_user):
        s = Session.objects.create(professeur=prof_user, titre='Del', langue='fr', duree_presentation=10)
        CritereNotation.objects.create(session=s, nom='C', coefficient=1.0, ordre=0)
        s_id = s.pk
        s.delete()
        assert not CritereNotation.objects.filter(session_id=s_id).exists()


# ============================================================================
# Modèle CritereNotation
# ============================================================================

@pytest.mark.django_db
class TestCritereNotationModel:

    def test_create_critere(self, session_obj):
        c = CritereNotation.objects.create(
            session=session_obj, nom='Originalité', coefficient=1.5,
            description='Aspect innovant', ordre=5,
        )
        assert c.pk is not None
        assert c.coefficient == 1.5
        assert c.est_personnalise is False

    def test_str_critere(self, session_obj):
        c = CritereNotation.objects.create(session=session_obj, nom='Clarté', coefficient=2.0, ordre=0)
        assert 'Clarté' in str(c)
        assert '2.0' in str(c)

    def test_ordering_by_ordre(self, session_obj):
        # Supprime les critères créés dans le fixture
        session_obj.criteres.all().delete()
        CritereNotation.objects.create(session=session_obj, nom='Z', coefficient=1.0, ordre=10)
        CritereNotation.objects.create(session=session_obj, nom='A', coefficient=1.0, ordre=1)
        CritereNotation.objects.create(session=session_obj, nom='M', coefficient=1.0, ordre=5)
        noms = list(session_obj.criteres.values_list('nom', flat=True))
        assert noms == ['A', 'M', 'Z']

    def test_est_personnalise_flag(self, session_obj):
        c = CritereNotation.objects.create(
            session=session_obj, nom='Custom', coefficient=1.0,
            est_personnalise=True, ordre=99,
        )
        assert c.est_personnalise is True


# ============================================================================
# Modèle PassageEtudiant
# ============================================================================

@pytest.mark.django_db
class TestPassageEtudiantModel:

    def test_create_passage(self, session_obj, etudiant_user):
        p = PassageEtudiant.objects.create(
            session=session_obj,
            heure_prevue=timezone.now(),
            ordre_passage=1,
        )
        p.etudiants.add(etudiant_user)
        assert p.pk is not None
        assert p.statut == 'en_attente'
        assert p.etudiants.count() == 1

    def test_str_with_student(self, passage_obj, etudiant_user):
        s = str(passage_obj)
        assert 'Alice Dupont' in s
        assert 'Session Test ML' in s

    def test_str_without_students(self, session_obj):
        p = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=5,
        )
        assert '(vide)' in str(p)

    def test_noms_etudiants_property(self, passage_groupe, etudiant_user, etudiant_user2):
        noms = passage_groupe.noms_etudiants
        assert 'Alice Dupont' in noms
        assert 'Bob Leroy' in noms

    def test_statut_choices(self, session_obj, etudiant_user):
        for code, _ in PassageEtudiant.STATUT_CHOICES:
            p = PassageEtudiant.objects.create(
                session=session_obj, heure_prevue=timezone.now(),
                ordre_passage=1, statut=code,
            )
            assert p.statut == code
            p.delete()

    def test_passage_m2m_multiple_students(self, passage_groupe, etudiant_user, etudiant_user2):
        assert passage_groupe.etudiants.count() == 2
        assert etudiant_user in passage_groupe.etudiants.all()
        assert etudiant_user2 in passage_groupe.etudiants.all()

    def test_donnees_posture_default_empty_dict(self, session_obj, etudiant_user):
        p = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=1,
        )
        assert p.donnees_posture == {}

    def test_date_debut_fin_nullable(self, passage_obj):
        assert passage_obj.date_debut is None
        assert passage_obj.date_fin is None

    def test_cascade_delete_from_session(self, session_obj, etudiant_user):
        p = PassageEtudiant.objects.create(
            session=session_obj, heure_prevue=timezone.now(), ordre_passage=1,
        )
        p_id = p.pk
        session_obj.delete()
        assert not PassageEtudiant.objects.filter(pk=p_id).exists()


# ============================================================================
# Modèle NoteIA
# ============================================================================

@pytest.mark.django_db
class TestNoteIAModel:

    def test_create_note_ia(self, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        note = NoteIA.objects.create(
            passage=passage_obj,
            etudiant=etudiant_user,
            critere=critere,
            note_ia=15.0,
            note_finale=15.0,
            commentaire_ia='Bonne présentation.',
        )
        assert note.pk is not None
        assert note.note_ia == 15.0
        assert note.modifiee_par_prof is False

    def test_note_finale_defaults_to_note_ia_on_create(self, passage_obj, etudiant_user, session_obj):
        """note_finale doit être = note_ia quand pk is None (nouvelle note)."""
        critere = session_obj.criteres.first()
        note = NoteIA(
            passage=passage_obj,
            etudiant=etudiant_user,
            critere=critere,
            note_ia=12.5,
            note_finale=None,
        )
        note.save()
        assert note.note_finale == 12.5

    def test_note_finale_not_overwritten_on_update(self, passage_obj, etudiant_user, session_obj):
        """note_finale ne doit pas être écrasée par note_ia lors d'une mise à jour."""
        critere = session_obj.criteres.first()
        note = NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user, critere=critere,
            note_ia=15.0, note_finale=18.0,  # prof a modifié
        )
        note.note_ia = 14.0
        note.save()
        note.refresh_from_db()
        assert note.note_finale == 18.0  # non écrasée

    def test_unique_together_constraint(self, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user, critere=critere,
            note_ia=10.0, note_finale=10.0,
        )
        with pytest.raises(IntegrityError):
            NoteIA.objects.create(
                passage=passage_obj, etudiant=etudiant_user, critere=critere,
                note_ia=12.0, note_finale=12.0,
            )

    def test_str_note_ia(self, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        note = NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user, critere=critere,
            note_ia=16.0, note_finale=16.0,
        )
        s = str(note)
        assert '16.0/20' in s

    def test_modifiee_par_prof_flag(self, passage_obj, etudiant_user, session_obj):
        critere = session_obj.criteres.first()
        note = NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user, critere=critere,
            note_ia=12.0, note_finale=14.0, modifiee_par_prof=True,
        )
        assert note.modifiee_par_prof is True

    def test_ordering_by_critere_ordre(self, passage_obj, etudiant_user, session_obj):
        criteres = list(session_obj.criteres.order_by('ordre'))
        for i, c in enumerate(criteres):
            NoteIA.objects.create(
                passage=passage_obj, etudiant=etudiant_user, critere=c,
                note_ia=float(10 + i), note_finale=float(10 + i),
            )
        notes = list(NoteIA.objects.filter(passage=passage_obj, etudiant=etudiant_user))
        assert notes[0].critere.ordre <= notes[-1].critere.ordre


# ============================================================================
# Modèle QuestionPosee
# ============================================================================

@pytest.mark.django_db
class TestQuestionPoseeModel:

    def test_create_question_ia(self, passage_obj):
        q = QuestionPosee.objects.create(
            passage=passage_obj,
            auteur='ia',
            question='Quelle est la complexité algorithmique de votre solution ?',
            reponse_etudiant='O(n log n) grâce au tri rapide.',
            evaluation_ia='Réponse correcte et précise.',
            note_reponse=15.0,
        )
        assert q.pk is not None
        assert q.auteur == 'ia'

    def test_create_question_prof(self, passage_obj):
        q = QuestionPosee.objects.create(
            passage=passage_obj,
            auteur='prof',
            question='Pourquoi avez-vous choisi cette architecture ?',
        )
        assert q.auteur == 'prof'
        assert q.note_reponse is None

    def test_str_question(self, passage_obj):
        q = QuestionPosee.objects.create(
            passage=passage_obj,
            auteur='ia',
            question='Expliquez les avantages de votre approche par rapport aux alternatives.',
        )
        s = str(q)
        assert 'ia' in s
        assert 'Expliquez' in s

    def test_str_truncated_at_60_chars(self, passage_obj):
        long_q = 'A' * 100
        q = QuestionPosee.objects.create(passage=passage_obj, auteur='ia', question=long_q)
        assert len(str(q)) < len(long_q) + 20  # str contient au plus 60 chars de la question

    def test_ordering_by_date_posee(self, passage_obj):
        q1 = QuestionPosee.objects.create(passage=passage_obj, auteur='ia', question='Q1')
        q2 = QuestionPosee.objects.create(passage=passage_obj, auteur='ia', question='Q2')
        questions = list(QuestionPosee.objects.filter(passage=passage_obj))
        assert questions[0] == q1
        assert questions[1] == q2

    def test_cascade_delete_with_passage(self, passage_obj):
        QuestionPosee.objects.create(passage=passage_obj, auteur='ia', question='Q')
        passage_id = passage_obj.pk
        passage_obj.delete()
        assert not QuestionPosee.objects.filter(passage_id=passage_id).exists()
