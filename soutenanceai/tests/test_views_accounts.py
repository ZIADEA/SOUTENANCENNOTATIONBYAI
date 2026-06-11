"""Tests des vues d'authentification et de gestion des comptes."""
import pytest
from django.urls import reverse

from accounts.models import User


# ============================================================================
# Login / Logout
# ============================================================================

@pytest.mark.django_db
class TestLoginView:

    def test_get_login_page(self, client):
        url = reverse('accounts:login')
        resp = client.get(url)
        assert resp.status_code == 200
        assert 'form' in resp.context

    def test_valid_login_redirects(self, client, prof_user):
        url = reverse('accounts:login')
        resp = client.post(url, {'username': 'prof_test', 'password': 'ProfPass123!'})
        assert resp.status_code == 302
        assert reverse('accounts:dashboard_redirect') in resp['Location']

    def test_invalid_password_shows_error(self, client, prof_user):
        url = reverse('accounts:login')
        resp = client.post(url, {'username': 'prof_test', 'password': 'mauvais'})
        assert resp.status_code == 200
        messages = list(resp.wsgi_request._messages)
        assert any('nvalid' in str(m) or 'nvalide' in str(m).lower() for m in messages)

    def test_unknown_username_shows_error(self, client):
        url = reverse('accounts:login')
        resp = client.post(url, {'username': 'inconnu', 'password': 'nimporte'})
        assert resp.status_code == 200

    def test_already_authenticated_redirects(self, client_prof):
        url = reverse('accounts:login')
        resp = client_prof.get(url)
        assert resp.status_code == 302

    def test_empty_form_shows_form(self, client):
        url = reverse('accounts:login')
        resp = client.post(url, {})
        assert resp.status_code == 200


@pytest.mark.django_db
class TestLogoutView:

    def test_logout_redirects_to_login(self, client_prof):
        url = reverse('accounts:logout')
        resp = client_prof.get(url)
        assert resp.status_code == 302
        assert 'login' in resp['Location']

    def test_logout_unauthenticated_still_redirects(self, client):
        url = reverse('accounts:logout')
        resp = client.get(url)
        assert resp.status_code == 302


# ============================================================================
# Dashboard redirect selon rôle
# ============================================================================

@pytest.mark.django_db
class TestDashboardRedirect:

    def test_unauthenticated_redirects_to_login(self, client):
        url = reverse('accounts:dashboard_redirect')
        resp = client.get(url)
        assert resp.status_code == 302
        assert 'login' in resp['Location']

    def test_professeur_redirected_to_sessions(self, client_prof):
        url = reverse('accounts:dashboard_redirect')
        resp = client_prof.get(url)
        assert resp.status_code == 302
        assert 'sessions' in resp['Location']

    def test_etudiant_redirected_to_presentation(self, client_etudiant):
        url = reverse('accounts:dashboard_redirect')
        resp = client_etudiant.get(url)
        assert resp.status_code == 302
        assert 'presentation' in resp['Location']

    def test_superadmin_redirected_to_admin(self, client_admin):
        url = reverse('accounts:dashboard_redirect')
        resp = client_admin.get(url)
        assert resp.status_code == 302
        assert 'admin' in resp['Location']


# ============================================================================
# Dashboard superadmin
# ============================================================================

@pytest.mark.django_db
class TestDashboardSuperadmin:

    def test_superadmin_can_access(self, client_admin):
        url = reverse('accounts:dashboard_superadmin')
        resp = client_admin.get(url)
        assert resp.status_code == 200
        assert 'stats' in resp.context

    def test_stats_are_correct(self, client_admin, prof_user, etudiant_user, session_obj):
        url = reverse('accounts:dashboard_superadmin')
        resp = client_admin.get(url)
        assert resp.context['stats']['nb_profs'] >= 1
        assert resp.context['stats']['nb_etudiants'] >= 1
        assert resp.context['stats']['nb_sessions'] >= 1

    def test_professeur_denied(self, client_prof):
        url = reverse('accounts:dashboard_superadmin')
        resp = client_prof.get(url)
        assert resp.status_code == 403

    def test_etudiant_denied(self, client_etudiant):
        url = reverse('accounts:dashboard_superadmin')
        resp = client_etudiant.get(url)
        assert resp.status_code == 403

    def test_anonymous_redirects_to_login(self, client):
        url = reverse('accounts:dashboard_superadmin')
        resp = client.get(url)
        assert resp.status_code == 302


# ============================================================================
# Création de professeur (superadmin seulement)
# ============================================================================

@pytest.mark.django_db
class TestCreerProfesseur:

    def test_get_form_as_superadmin(self, client_admin):
        url = reverse('accounts:creer_professeur')
        resp = client_admin.get(url)
        assert resp.status_code == 200
        assert 'form' in resp.context

    def test_post_creates_professeur(self, client_admin):
        url = reverse('accounts:creer_professeur')
        data = {
            'username': 'nouveau_prof',
            'first_name': 'Nouveau',
            'last_name': 'Professeur',
            'email': 'nouveau@test.com',
            'sexe': 'H',
            'password1': 'ProfPass999!',
            'password2': 'ProfPass999!',
        }
        resp = client_admin.post(url, data)
        assert resp.status_code == 302
        u = User.objects.get(username='nouveau_prof')
        assert u.role == User.ROLE_PROFESSEUR
        assert u.cree_par is not None

    def test_professeur_cannot_create_professeur(self, client_prof):
        url = reverse('accounts:creer_professeur')
        resp = client_prof.get(url)
        assert resp.status_code == 403

    def test_duplicate_username_shows_form_error(self, client_admin, prof_user):
        url = reverse('accounts:creer_professeur')
        data = {
            'username': 'prof_test',  # déjà existant
            'password1': 'ProfPass999!',
            'password2': 'ProfPass999!',
        }
        resp = client_admin.post(url, data)
        assert resp.status_code == 200  # reste sur le form


# ============================================================================
# Liste professeurs
# ============================================================================

@pytest.mark.django_db
class TestListeProfesseurs:

    def test_superadmin_sees_all_profs(self, client_admin, prof_user, prof_user2):
        url = reverse('accounts:liste_professeurs')
        resp = client_admin.get(url)
        assert resp.status_code == 200
        usernames = [u.username for u in resp.context['utilisateurs']]
        assert 'prof_test' in usernames
        assert 'prof_test2' in usernames

    def test_prof_denied(self, client_prof):
        url = reverse('accounts:liste_professeurs')
        resp = client_prof.get(url)
        assert resp.status_code == 403


# ============================================================================
# Création d'étudiant (professeur ou superadmin)
# ============================================================================

@pytest.mark.django_db
class TestCreerEtudiant:

    def test_prof_can_get_form(self, client_prof):
        url = reverse('accounts:creer_etudiant')
        resp = client_prof.get(url)
        assert resp.status_code == 200

    def test_prof_post_creates_etudiant(self, client_prof, prof_user):
        url = reverse('accounts:creer_etudiant')
        data = {
            'username': 'new_etu',
            'first_name': 'New',
            'last_name': 'Student',
            'email': 'new@test.com',
            'password1': 'EtudPass999!',
            'password2': 'EtudPass999!',
        }
        resp = client_prof.post(url, data)
        assert resp.status_code == 302
        u = User.objects.get(username='new_etu')
        assert u.role == User.ROLE_ETUDIANT
        assert u.cree_par == prof_user

    def test_etudiant_denied(self, client_etudiant):
        url = reverse('accounts:creer_etudiant')
        resp = client_etudiant.get(url)
        assert resp.status_code == 403


# ============================================================================
# Liste étudiants
# ============================================================================

@pytest.mark.django_db
class TestListeEtudiants:

    def test_prof_sees_only_own_students(self, client_prof, etudiant_user, etudiant_autre_prof):
        url = reverse('accounts:liste_etudiants')
        resp = client_prof.get(url)
        assert resp.status_code == 200
        usernames = [u.username for u in resp.context['utilisateurs']]
        assert 'etudiant_test' in usernames
        assert 'etudiant_autre' not in usernames

    def test_superadmin_sees_all_students(self, client_admin, etudiant_user, etudiant_autre_prof):
        url = reverse('accounts:liste_etudiants')
        resp = client_admin.get(url)
        assert resp.status_code == 200
        usernames = [u.username for u in resp.context['utilisateurs']]
        assert 'etudiant_test' in usernames
        assert 'etudiant_autre' in usernames


# ============================================================================
# Suppression d'utilisateur
# ============================================================================

@pytest.mark.django_db
class TestSupprimerUtilisateur:

    def test_prof_can_delete_own_student(self, client_prof, etudiant_user):
        url = reverse('accounts:supprimer_utilisateur', args=[etudiant_user.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 302
        assert not User.objects.filter(pk=etudiant_user.pk).exists()

    def test_prof_cannot_delete_other_prof_student(self, client_prof, etudiant_autre_prof):
        url = reverse('accounts:supprimer_utilisateur', args=[etudiant_autre_prof.pk])
        resp = client_prof.post(url)
        assert resp.status_code == 302
        assert User.objects.filter(pk=etudiant_autre_prof.pk).exists()

    def test_superadmin_can_delete_any_user(self, client_admin, etudiant_user):
        url = reverse('accounts:supprimer_utilisateur', args=[etudiant_user.pk])
        resp = client_admin.post(url)
        assert resp.status_code == 302
        assert not User.objects.filter(pk=etudiant_user.pk).exists()

    def test_get_does_not_delete(self, client_prof, etudiant_user):
        url = reverse('accounts:supprimer_utilisateur', args=[etudiant_user.pk])
        resp = client_prof.get(url)
        assert resp.status_code == 302
        assert User.objects.filter(pk=etudiant_user.pk).exists()
