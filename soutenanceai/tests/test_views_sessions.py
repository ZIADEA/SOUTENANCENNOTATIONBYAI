"""Tests des vues du dashboard professeur et gestion de sessions."""
import pytest
from django.urls import reverse
from django.utils import timezone

from sessions_app.models import Classe, CritereNotation, PassageEtudiant, Session


# ============================================================================
# Dashboard professeur (liste des classes)
# ============================================================================

@pytest.mark.django_db
class TestDashboardProfesseur:

    def test_prof_sees_own_classes(self, client_prof, classe_obj):
        url = reverse('sessions_app:dashboard_professeur')
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert classe_obj in resp.context['classes']

    def test_prof_does_not_see_other_profs_classes(self, client_prof, prof_user2, db):
        c2 = Classe.objects.create(professeur=prof_user2, nom='Classe Autre Prof')
        url = reverse('sessions_app:dashboard_professeur')
        resp = client_prof.get(url)
        assert c2 not in resp.context['classes']

    def test_anonymous_redirected(self, client):
        url = reverse('sessions_app:dashboard_professeur')
        resp = client.get(url)
        assert resp.status_code == 302
        assert 'login' in resp['Location']

    def test_etudiant_denied(self, client_etudiant):
        url = reverse('sessions_app:dashboard_professeur')
        resp = client_etudiant.get(url)
        assert resp.status_code == 403


# ============================================================================
# Création de session
# ============================================================================

@pytest.mark.django_db
class TestCreerSession:

    SESSION_POST = {
        'titre': 'Nouvelle Session Test',
        'description': 'Description de test',
        'langue': 'fr',
        'duree_presentation': 15,
        'duree_questions': 5,
        'nb_questions_max': 3,
        'coefficient_rapport': '1.0',
        'coefficient_demo_video': '1.0',
        'coefficient_github': '1.0',
        'style_questionnement': 'mentor',
        'style_notation': 'juste',
        'consignes_ia': '',
        'mode_notation_groupe': 'individuelle',
        'coefficient_groupe': '0.5',
        'coefficient_individuel': '0.5',
    }

    def _url(self, classe):
        return reverse('sessions_app:creer_session', args=[classe.pk])

    def test_get_form(self, client_prof, classe_obj):
        resp = client_prof.get(self._url(classe_obj))
        assert resp.status_code == 200
        assert 'form' in resp.context
        assert 'criteres_predefinis' in resp.context

    def test_post_creates_session(self, client_prof, prof_user, classe_obj):
        resp = client_prof.post(self._url(classe_obj), self.SESSION_POST)
        assert resp.status_code == 302
        assert Session.objects.filter(titre='Nouvelle Session Test', professeur=prof_user).exists()

    def test_session_attached_to_classe(self, client_prof, classe_obj):
        client_prof.post(self._url(classe_obj), self.SESSION_POST)
        session = Session.objects.get(titre='Nouvelle Session Test')
        assert session.classe == classe_obj

    def test_post_with_predefined_criteria(self, client_prof, prof_user, classe_obj):
        data = dict(self.SESSION_POST)
        data['critere_predef_Structure'] = 'on'
        data['coef_predef_Structure'] = '2.0'
        resp = client_prof.post(self._url(classe_obj), data)
        assert resp.status_code == 302
        session = Session.objects.get(titre='Nouvelle Session Test', professeur=prof_user)
        c = session.criteres.get(nom='Structure')
        assert c.est_personnalise is False
        assert c.coefficient == 2.0

    def test_post_with_custom_criteria(self, client_prof, prof_user, classe_obj):
        data = dict(self.SESSION_POST)
        data['critere_perso_0'] = 'Mon Critère Personnel'
        data['coef_perso_0'] = '1.5'
        resp = client_prof.post(self._url(classe_obj), data)
        assert resp.status_code == 302
        session = Session.objects.get(titre='Nouvelle Session Test', professeur=prof_user)
        c = session.criteres.get(nom='Mon Critère Personnel')
        assert c.est_personnalise is True
        assert c.coefficient == 1.5

    def test_prof_set_as_professeur_automatically(self, client_prof, prof_user, classe_obj):
        client_prof.post(self._url(classe_obj), self.SESSION_POST)
        session = Session.objects.get(titre='Nouvelle Session Test')
        assert session.professeur == prof_user

    def test_empty_title_stays_on_form(self, client_prof, classe_obj):
        data = dict(self.SESSION_POST)
        data['titre'] = ''
        resp = client_prof.post(self._url(classe_obj), data)
        assert resp.status_code == 200  # reste sur le formulaire

    def test_cannot_create_in_other_profs_classe(self, client_prof, prof_user2, db):
        c2 = Classe.objects.create(professeur=prof_user2, nom='Classe Protégée')
        resp = client_prof.get(self._url(c2))
        assert resp.status_code == 404

    def test_etudiant_denied(self, client_etudiant, classe_obj):
        resp = client_etudiant.get(self._url(classe_obj))
        assert resp.status_code == 403


# ============================================================================
# Détail session
# ============================================================================

@pytest.mark.django_db
class TestDetailSession:

    def test_prof_sees_own_session(self, client_prof, session_obj, passage_obj):
        url = reverse('sessions_app:detail_session', args=[session_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert resp.context['session'] == session_obj
        assert passage_obj in resp.context['passages']

    def test_prof_cannot_see_other_profs_session(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Pas la mienne',
            langue='fr', duree_presentation=10,
        )
        url = reverse('sessions_app:detail_session', args=[s2.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 404

    def test_criteres_in_context(self, client_prof, session_obj):
        url = reverse('sessions_app:detail_session', args=[session_obj.pk])
        resp = client_prof.get(url)
        criteres = list(resp.context['criteres'])
        assert len(criteres) == 2


# ============================================================================
# Édition de session
# ============================================================================

@pytest.mark.django_db
class TestEditerSession:

    def test_get_edit_form(self, client_prof, session_obj):
        url = reverse('sessions_app:editer_session', args=[session_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert resp.context['form'].instance == session_obj

    EDIT_POST = {
        'description': '',
        'langue': 'fr',
        'duree_presentation': 15,
        'duree_questions': 5,
        'nb_questions_max': 3,
        'coefficient_rapport': '1.0',
        'coefficient_demo_video': '1.0',
        'coefficient_github': '1.0',
        'style_questionnement': 'mentor',
        'style_notation': 'juste',
        'consignes_ia': '',
        'mode_notation_groupe': 'individuelle',
        'coefficient_groupe': '0.5',
        'coefficient_individuel': '0.5',
    }

    def test_post_updates_title(self, client_prof, session_obj):
        url = reverse('sessions_app:editer_session', args=[session_obj.pk])
        data = dict(self.EDIT_POST, titre='Titre Modifié')
        resp = client_prof.post(url, data)
        assert resp.status_code == 302
        session_obj.refresh_from_db()
        assert session_obj.titre == 'Titre Modifié'

    def test_edit_replaces_old_criteria(self, client_prof, session_obj):
        """Les anciens critères doivent être supprimés et remplacés."""
        old_count = session_obj.criteres.count()
        assert old_count == 2
        url = reverse('sessions_app:editer_session', args=[session_obj.pk])
        data = dict(
            self.EDIT_POST,
            titre=session_obj.titre,
            # Un seul critère cette fois
            critere_predef_Structure='on',
            coef_predef_Structure='1.0',
        )
        client_prof.post(url, data)
        session_obj.refresh_from_db()
        assert session_obj.criteres.count() == 1

    def test_cannot_edit_other_profs_session(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Autre', langue='fr', duree_presentation=10,
        )
        url = reverse('sessions_app:editer_session', args=[s2.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 404


# ============================================================================
# Suppression de session
# ============================================================================

@pytest.mark.django_db
class TestSupprimerSession:

    def test_post_deletes_session(self, client_prof, session_obj):
        pk = session_obj.pk
        url = reverse('sessions_app:supprimer_session', args=[pk])
        resp = client_prof.post(url)
        assert resp.status_code == 302
        assert not Session.objects.filter(pk=pk).exists()

    def test_get_does_not_delete(self, client_prof, session_obj):
        pk = session_obj.pk
        url = reverse('sessions_app:supprimer_session', args=[pk])
        resp = client_prof.get(url)
        # GET on a POST-only view returns 405
        assert resp.status_code == 405
        assert Session.objects.filter(pk=pk).exists()

    def test_cannot_delete_other_profs_session(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Protégée', langue='fr', duree_presentation=10,
        )
        url = reverse('sessions_app:supprimer_session', args=[s2.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 404
        assert Session.objects.filter(pk=s2.pk).exists()


# ============================================================================
# Planification des passages (création inline via planifier_passages)
# ============================================================================

@pytest.mark.django_db
class TestPlanifierPassages:

    def test_get_form(self, client_prof, session_obj):
        url = reverse('sessions_app:planifier_passages', args=[session_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert 'form' in resp.context
        assert 'form_auto' in resp.context

    def test_post_creates_passage(self, client_prof, classe_obj, prof_user, etudiant_user):
        session = Session.objects.create(
            professeur=prof_user, titre='Session Classe', langue='fr',
            duree_presentation=10, classe=classe_obj,
        )
        url = reverse('sessions_app:planifier_passages', args=[session.pk])
        data = {
            'action': 'nouveau_passage',
            'etudiants': [etudiant_user.pk],
            'ordre_passage': 1,
            'heure_prevue': '2026-06-01T09:00',
        }
        resp = client_prof.post(url, data)
        assert resp.status_code == 302
        passage = PassageEtudiant.objects.get(session=session)
        assert passage.type_groupe == 'monome'
        assert etudiant_user in passage.etudiants.all()

    def test_cannot_plan_other_profs_session(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Autre', langue='fr', duree_presentation=10,
        )
        url = reverse('sessions_app:planifier_passages', args=[s2.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 404


# ============================================================================
# Édition / suppression de passage
# ============================================================================

@pytest.mark.django_db
class TestEditerSupprimerPassage:

    def test_edit_passage_get(self, client_prof, passage_obj):
        url = reverse('sessions_app:editer_passage', args=[passage_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200

    def test_delete_passage(self, client_prof, passage_obj):
        pk = passage_obj.pk
        url = reverse('sessions_app:supprimer_passage', args=[pk])
        resp = client_prof.post(url)
        assert resp.status_code == 302
        assert not PassageEtudiant.objects.filter(pk=pk).exists()

    def test_cannot_delete_other_profs_passage(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Autre', langue='fr', duree_presentation=10,
        )
        p2 = PassageEtudiant.objects.create(
            session=s2, heure_prevue=timezone.now(), ordre_passage=1,
        )
        url = reverse('sessions_app:supprimer_passage', args=[p2.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 404
        assert PassageEtudiant.objects.filter(pk=p2.pk).exists()


# ============================================================================
# Suivi live
# ============================================================================

@pytest.mark.django_db
class TestSuiviLive:

    def test_prof_can_access_live(self, client_prof, passage_obj):
        url = reverse('sessions_app:suivi_live', args=[passage_obj.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 200
        assert 'passage' in resp.context

    def test_cannot_access_other_profs_live(self, client_prof, prof_user2, db):
        s2 = Session.objects.create(
            professeur=prof_user2, titre='Autre', langue='fr', duree_presentation=10,
        )
        p2 = PassageEtudiant.objects.create(
            session=s2, heure_prevue=timezone.now(), ordre_passage=1,
        )
        url = reverse('sessions_app:suivi_live', args=[p2.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 404
