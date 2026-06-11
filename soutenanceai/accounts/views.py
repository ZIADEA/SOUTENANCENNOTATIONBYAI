"""Vues d'authentification et de gestion des comptes."""
import csv
import io
import secrets
import string
import unicodedata

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .decorators import etudiant_required, professeur_required, superadmin_required
from .forms import CreerCompteForm, CreerProfesseurForm, ImportCSVForm, InscriptionProfesseurForm, LoginForm, ProfilEtudiantForm
from .models import User


# ---- Helpers privés -------------------------------------------------------

def _normaliser_ascii(s: str) -> str:
    """Convertit une chaîne en ASCII minuscules sans accents ni caractères spéciaux."""
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_str = nfkd.encode('ascii', 'ignore').decode('ascii')
    return ''.join(c for c in ascii_str.lower() if c.isalnum() or c == '-')


def _generer_username(prenom: str, nom: str) -> str:
    """
    Génère un username de la forme prenom.nom en ASCII minuscules sans accents.
    Gère les doublons en cherchant le premier suffixe libre (_2, _3, ...).
    """
    base = f"{_normaliser_ascii(prenom)}.{_normaliser_ascii(nom)}"
    if base and not User.objects.filter(username=base).exists():
        return base
    i = 2
    while True:
        candidat = f"{base}_{i}"
        if not User.objects.filter(username=candidat).exists():
            return candidat
        i += 1


def _generer_mot_de_passe(n: int = 10) -> str:
    """Génère un mot de passe aléatoire alphanumérique de n caractères."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))


# ---- Landing & inscription ------------------------------------------------

def landing_view(request):
    """Page d'accueil publique. Redirige vers le dashboard si déjà connecté."""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard_redirect')
    return render(request, 'landing.html')


def inscription_professeur(request):
    """Auto-inscription pour les professeurs. Crée le compte et connecte directement."""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard_redirect')

    form = InscriptionProfesseurForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.role = User.ROLE_PROFESSEUR
        user.save()
        # Connexion automatique après inscription
        login(request, user)
        messages.success(
            request,
            f'Bienvenue {user.get_full_name() or user.username} ! '
            'Votre compte professeur est prêt. Créez votre première session de soutenance.'
        )
        return redirect('sessions_app:dashboard_professeur')

    return render(request, 'accounts/inscription_professeur.html', {'form': form})


# ---- Auth -----------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard_redirect')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['username'],
            password=form.cleaned_data['password'],
        )
        if user is not None:
            login(request, user)
            messages.success(request, f'Bienvenue {user.get_full_name() or user.username}.')
            return redirect('accounts:dashboard_redirect')
        messages.error(request, 'Identifiants invalides.')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'Vous êtes déconnecté.')
    return redirect('accounts:login')


@login_required
def dashboard_redirect(request):
    """Redirige vers le dashboard correspondant au rôle."""
    u = request.user
    if u.is_superadmin:
        return redirect('accounts:dashboard_superadmin')
    if u.is_professeur:
        return redirect('sessions_app:dashboard_professeur')
    return redirect('presentation:dashboard_etudiant')


# ---- Superadmin ----------------------------------------------------------

@superadmin_required
def dashboard_superadmin(request):
    from sessions_app.models import Session as SessionModel, PassageEtudiant
    from notation.models import NoteIA

    stats = {
        'nb_sessions': SessionModel.objects.count(),
        'nb_profs': User.objects.filter(role='professeur').count(),
        'nb_etudiants': User.objects.filter(role='etudiant').count(),
        'nb_passages': PassageEtudiant.objects.count(),
        'nb_passages_termines': PassageEtudiant.objects.filter(statut='termine').count(),
    }
    notes = NoteIA.objects.all()
    if notes.exists():
        from django.db.models import Avg
        stats['moyenne_notes'] = round(notes.aggregate(m=Avg('note_finale'))['m'] or 0, 2)
    else:
        stats['moyenne_notes'] = None

    profs_recents = User.objects.filter(role='professeur').order_by('-date_joined')[:10]
    return render(request, 'accounts/dashboard_superadmin.html', {
        'stats': stats, 'profs_recents': profs_recents,
    })


@superadmin_required
@require_http_methods(['GET', 'POST'])
def creer_professeur(request):
    form = CreerProfesseurForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.role = User.ROLE_PROFESSEUR
        user.cree_par = request.user
        user.save()
        messages.success(request, f'Compte professeur "{user.username}" créé.')
        return redirect('accounts:liste_professeurs')
    return render(request, 'accounts/creer_compte.html', {
        'form': form, 'titre': 'Créer un compte professeur', 'role': 'professeur',
    })


@superadmin_required
def liste_professeurs(request):
    profs = User.objects.filter(role='professeur').order_by('-date_joined')
    return render(request, 'accounts/liste_utilisateurs.html', {
        'utilisateurs': profs, 'titre': 'Professeurs', 'role': 'professeur',
    })


# ---- Professeur ----------------------------------------------------------

@professeur_required
@require_http_methods(['GET', 'POST'])
def creer_etudiant(request):
    form = CreerCompteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.role = User.ROLE_ETUDIANT
        user.cree_par = request.user
        user.save()
        messages.success(request, f'Compte étudiant "{user.username}" créé.')
        return redirect('accounts:liste_etudiants')
    return render(request, 'accounts/creer_compte.html', {
        'form': form, 'titre': 'Créer un compte étudiant', 'role': 'etudiant',
    })


@professeur_required
def liste_etudiants(request):
    """Le prof voit les étudiants qu'il a créés (ou tous s'il est superadmin)."""
    qs = User.objects.filter(role='etudiant')
    if not request.user.is_superadmin:
        qs = qs.filter(cree_par=request.user)
    return render(request, 'accounts/liste_utilisateurs.html', {
        'utilisateurs': qs.order_by('-date_joined'),
        'titre': 'Étudiants', 'role': 'etudiant',
    })


@professeur_required
@require_http_methods(['GET', 'POST'])
def importer_etudiants_csv(request):
    """Import en masse d'étudiants depuis un fichier CSV."""
    form = ImportCSVForm(request.POST or None, request.FILES or None)
    resultats = None

    if request.method == 'POST' and form.is_valid():
        fichier = request.FILES['fichier_csv']

        # Lire et décoder le fichier (gère BOM UTF-8 produit par Excel)
        contenu = fichier.read()
        try:
            texte = contenu.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                texte = contenu.decode('latin-1')
            except UnicodeDecodeError:
                messages.error(request, "Impossible de lire le fichier. Utilisez l'encodage UTF-8.")
                return render(request, 'accounts/importer_etudiants.html',
                              {'form': form, 'resultats': None})

        # Détecter le séparateur (virgule ou point-virgule — Excel FR utilise ;)
        try:
            dialect = csv.Sniffer().sniff(texte[:2048], delimiters=',;\t')
            reader = csv.DictReader(io.StringIO(texte), dialect=dialect)
        except csv.Error:
            reader = csv.DictReader(io.StringIO(texte))  # fallback virgule

        # Normaliser les noms de colonnes
        fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames

        colonnes_requises = {'prenom', 'nom', 'email'}
        if not colonnes_requises.issubset(set(fieldnames)):
            manquantes = colonnes_requises - set(fieldnames)
            messages.error(
                request,
                f"Colonnes manquantes dans le CSV : {', '.join(sorted(manquantes))}. "
                "Le fichier doit avoir les colonnes : prenom, nom, email"
            )
            return render(request, 'accounts/importer_etudiants.html',
                          {'form': form, 'resultats': None})

        resultats = []
        crees = []  # liste pour le téléchargement CSV

        for i, ligne in enumerate(reader, start=2):  # ligne 1 = en-tête
            prenom = (ligne.get('prenom') or '').strip()
            nom    = (ligne.get('nom') or '').strip()
            email  = (ligne.get('email') or '').strip()

            # Ignorer les lignes complètement vides
            if not prenom and not nom and not email:
                continue

            if not prenom or not nom:
                resultats.append({
                    'ligne': i, 'prenom': prenom, 'nom': nom, 'email': email,
                    'statut': 'erreur', 'detail': 'Prénom ou nom manquant',
                    'username': '', 'password': '',
                })
                continue

            # Vérifier doublon email
            if email and User.objects.filter(email=email).exists():
                resultats.append({
                    'ligne': i, 'prenom': prenom, 'nom': nom, 'email': email,
                    'statut': 'ignore', 'detail': 'Email déjà utilisé',
                    'username': '', 'password': '',
                })
                continue

            username = _generer_username(prenom, nom)
            password = _generer_mot_de_passe()

            try:
                u = User(
                    username=username,
                    first_name=prenom,
                    last_name=nom,
                    email=email,
                    role=User.ROLE_ETUDIANT,
                    cree_par=request.user,
                )
                u.set_password(password)
                u.save()
                crees.append({
                    'prenom': prenom, 'nom': nom, 'email': email,
                    'username': username, 'password': password,
                })
                resultats.append({
                    'ligne': i, 'prenom': prenom, 'nom': nom, 'email': email,
                    'statut': 'cree', 'detail': '',
                    'username': username, 'password': password,
                })
            except Exception as exc:
                resultats.append({
                    'ligne': i, 'prenom': prenom, 'nom': nom, 'email': email,
                    'statut': 'erreur', 'detail': str(exc),
                    'username': '', 'password': '',
                })

        # Stocker les identifiants en session pour le téléchargement
        request.session['csv_import_crees'] = crees

        nb_crees = sum(1 for r in resultats if r['statut'] == 'cree')
        nb_ignores = sum(1 for r in resultats if r['statut'] == 'ignore')
        nb_erreurs = sum(1 for r in resultats if r['statut'] == 'erreur')
        messages.success(
            request,
            f"{nb_crees} étudiant(s) créé(s), {nb_ignores} ignoré(s), {nb_erreurs} erreur(s)."
        )

    return render(request, 'accounts/importer_etudiants.html',
                  {'form': form, 'resultats': resultats})


@professeur_required
def telecharger_credentials_csv(request):
    """Renvoie le CSV des identifiants créés lors du dernier import (usage unique)."""
    crees = request.session.pop('csv_import_crees', [])

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="identifiants_etudiants.csv"'

    # BOM UTF-8 pour Excel (ouverture correcte des accents)
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow(['prenom', 'nom', 'email', 'username', 'mot_de_passe'])
    for etu in crees:
        writer.writerow([
            etu['prenom'], etu['nom'], etu['email'],
            etu['username'], etu['password'],
        ])
    return response


# ---- Commun ---------------------------------------------------------------

@login_required
def supprimer_utilisateur(request, user_id):
    cible = get_object_or_404(User, pk=user_id)
    autorise = (
        request.user.is_superadmin
        or (request.user.is_professeur and cible.cree_par_id == request.user.id)
    )
    if not autorise:
        messages.error(request, "Action non autorisée.")
        return redirect('accounts:dashboard_redirect')
    role_cible = cible.role  # mémoriser avant delete
    if request.method == 'POST':
        cible.delete()
        messages.success(request, "Utilisateur supprimé.")
    if role_cible == 'professeur':
        return redirect('accounts:liste_professeurs')
    return redirect('accounts:liste_etudiants')


@login_required
@require_http_methods(['POST'])
def reinitialiser_mot_de_passe(request, user_id):
    """
    Réinitialise le mot de passe d'un utilisateur et affiche le nouveau en clair.
    POST uniquement — protège contre les resets accidentels via lien GET.
    """
    cible = get_object_or_404(User, pk=user_id)

    autorise = (
        request.user.is_superadmin
        or (request.user.is_professeur and cible.cree_par_id == request.user.id)
    )
    if not autorise:
        messages.error(request, "Action non autorisée.")
        return redirect('accounts:dashboard_redirect')

    nouveau_mdp = _generer_mot_de_passe()
    cible.set_password(nouveau_mdp)
    cible.save()

    nom_affiche = cible.get_full_name() or cible.username
    messages.success(
        request,
        f"Mot de passe de {nom_affiche} réinitialisé. "
        f"Nouveau mot de passe : {nouveau_mdp}"
    )

    if cible.role == User.ROLE_PROFESSEUR:
        return redirect('accounts:liste_professeurs')
    return redirect('accounts:liste_etudiants')


# ============================================================================
# Profil étudiant — photo de profil pour la reconnaissance faciale
# ============================================================================

@login_required
@require_http_methods(['GET', 'POST'])
def modifier_profil(request):
    """Permet à n'importe quel utilisateur connecté de mettre à jour sa photo de profil."""
    form = ProfilEtudiantForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Photo de profil mise à jour.')
        return redirect('accounts:modifier_profil')
    return render(request, 'accounts/profil.html', {'form': form})
