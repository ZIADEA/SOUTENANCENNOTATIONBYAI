"""Fixtures partagées entre tous les tests."""
import pytest
from django.utils import timezone

from accounts.models import User
from sessions_app.models import Classe, CritereNotation, PassageEtudiant, Session


# ============================================================================
# Utilisateurs
# ============================================================================

@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username='admin_test',
        password='AdminPass123!',
        role=User.ROLE_SUPERADMIN,
        is_superuser=True,
        first_name='Super',
        last_name='Admin',
    )


@pytest.fixture
def prof_user(db):
    return User.objects.create_user(
        username='prof_test',
        password='ProfPass123!',
        role=User.ROLE_PROFESSEUR,
        first_name='Marie',
        last_name='Martin',
    )


@pytest.fixture
def prof_user2(db):
    """Second professeur — pour tester l'isolation entre profs."""
    return User.objects.create_user(
        username='prof_test2',
        password='ProfPass123!',
        role=User.ROLE_PROFESSEUR,
        first_name='Jean',
        last_name='Dupuis',
    )


@pytest.fixture
def etudiant_user(db, prof_user):
    return User.objects.create_user(
        username='etudiant_test',
        password='EtudPass123!',
        role=User.ROLE_ETUDIANT,
        first_name='Alice',
        last_name='Dupont',
        cree_par=prof_user,
    )


@pytest.fixture
def etudiant_user2(db, prof_user):
    return User.objects.create_user(
        username='etudiant_test2',
        password='EtudPass123!',
        role=User.ROLE_ETUDIANT,
        first_name='Bob',
        last_name='Leroy',
        cree_par=prof_user,
    )


@pytest.fixture
def etudiant_autre_prof(db, prof_user2):
    """Étudiant appartenant à un autre professeur."""
    return User.objects.create_user(
        username='etudiant_autre',
        password='EtudPass123!',
        role=User.ROLE_ETUDIANT,
        cree_par=prof_user2,
    )


# ============================================================================
# Classes, sessions et passages
# ============================================================================

@pytest.fixture
def classe_obj(db, prof_user, etudiant_user):
    """Classe créée par prof_user avec etudiant_user inscrit."""
    c = Classe.objects.create(professeur=prof_user, nom='Classe Test L3')
    c.inscrits.add(etudiant_user)
    return c


@pytest.fixture
def session_obj(db, prof_user):
    s = Session.objects.create(
        professeur=prof_user,
        titre='Session Test ML',
        langue='fr',
        duree_presentation=15,
        duree_questions=5,
        nb_questions_max=3,
        style_questionnement='mentor',
        style_notation='juste',
        mode_notation_groupe='individuelle',
    )
    CritereNotation.objects.create(session=s, nom="Clarté de l'expression", coefficient=1.0, ordre=0)
    CritereNotation.objects.create(session=s, nom='Structure', coefficient=2.0, ordre=1)
    return s


@pytest.fixture
def session_identique(db, prof_user):
    """Session en mode notation identique pour tout le groupe."""
    s = Session.objects.create(
        professeur=prof_user,
        titre='Session Groupe Identique',
        langue='fr',
        duree_presentation=20,
        nb_questions_max=2,
        style_questionnement='perfectionniste',
        style_notation='severe',
        mode_notation_groupe='identique',
    )
    CritereNotation.objects.create(session=s, nom='Clarté', coefficient=1.0, ordre=0)
    return s


@pytest.fixture
def passage_obj(db, session_obj, etudiant_user):
    p = PassageEtudiant.objects.create(
        session=session_obj,
        heure_prevue=timezone.now(),
        ordre_passage=1,
        type_groupe='monome',
    )
    p.etudiants.add(etudiant_user)
    return p


@pytest.fixture
def passage_groupe(db, session_obj, etudiant_user, etudiant_user2):
    p = PassageEtudiant.objects.create(
        session=session_obj,
        heure_prevue=timezone.now(),
        ordre_passage=2,
        type_groupe='binome',
    )
    p.etudiants.add(etudiant_user, etudiant_user2)
    return p


@pytest.fixture
def passage_termine(db, session_obj, etudiant_user):
    """Passage terminé avec transcription et dates."""
    p = PassageEtudiant.objects.create(
        session=session_obj,
        heure_prevue=timezone.now(),
        ordre_passage=3,
        statut='termine',
        transcription='Bonjour, je vais vous présenter mon projet de machine learning.',
        date_debut=timezone.now(),
        date_fin=timezone.now(),
    )
    p.etudiants.add(etudiant_user)
    return p


# ============================================================================
# Clients HTTP authentifiés
# ============================================================================

@pytest.fixture
def client_prof(client, prof_user):
    client.force_login(prof_user)
    return client


@pytest.fixture
def client_etudiant(client, etudiant_user):
    client.force_login(etudiant_user)
    return client


@pytest.fixture
def client_admin(client, admin_user):
    client.force_login(admin_user)
    return client
