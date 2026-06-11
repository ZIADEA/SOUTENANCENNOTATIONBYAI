from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import ChangePasswordForm

app_name = 'accounts'

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('inscription/', views.inscription_professeur, name='inscription_professeur'),

    # Superadmin
    path('admin/', views.dashboard_superadmin, name='dashboard_superadmin'),
    path('admin/professeurs/', views.liste_professeurs, name='liste_professeurs'),
    path('admin/professeurs/nouveau/', views.creer_professeur, name='creer_professeur'),

    # Professeur — gestion étudiants
    path('etudiants/', views.liste_etudiants, name='liste_etudiants'),
    path('etudiants/nouveau/', views.creer_etudiant, name='creer_etudiant'),
    path('etudiants/importer/', views.importer_etudiants_csv, name='importer_etudiants_csv'),
    path('etudiants/importer/telecharger/', views.telecharger_credentials_csv,
         name='telecharger_credentials_csv'),

    # Changement de mot de passe self-service (tous rôles)
    path('mot-de-passe/changer/',
         auth_views.PasswordChangeView.as_view(
             template_name='accounts/changer_mot_de_passe.html',
             form_class=ChangePasswordForm,
             success_url=reverse_lazy('accounts:password_change_done'),
         ),
         name='changer_mot_de_passe'),
    path('mot-de-passe/change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='accounts/changer_mot_de_passe_done.html',
         ),
         name='password_change_done'),

    # Commun
    path('<int:user_id>/supprimer/', views.supprimer_utilisateur, name='supprimer_utilisateur'),
    path('<int:user_id>/reinitialiser-mdp/', views.reinitialiser_mot_de_passe,
         name='reinitialiser_mot_de_passe'),

    # Profil — photo pour reconnaissance faciale
    path('profil/', views.modifier_profil, name='modifier_profil'),
]
