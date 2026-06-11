"""
Script d'inscription en masse des étudiants de la classe 4A IATDSI 2026.
Usage : .venv\Scripts\python.exe manage.py shell < inscrire_etudiants.py
"""
import unicodedata
import re
from django.db import transaction
from accounts.models import User
from sessions_app.models import Classe

# ── Données extraites de l'image ─────────────────────────────────────────────
# Format : (numéro_groupe, [(nom_famille, prenom), ...])
# Ligne 14 ignorée (doublon de la ligne 17 + Fatima Akebli)

GROUPES_DATA = [
    (1,  [("Zbida",              "Mohamed Amine"),
          ("Essahraoui",         "Amine")]),

    (2,  [("Elhakioui",          "Asmae"),
          ("Mohamed",            "Reda Nkira")]),

    (3,  [("El Khamkhoumi",      "Naoufal"),
          ("Serraji",            "Wiam"),
          ("Mokhass",            "Yassine")]),

    (4,  [("Errita",             "Yasser")]),

    (5,  [("Daoudi",             "Sohaib"),
          ("Majidi",             "Marouane"),
          ("Boudrika",           "Ilias")]),

    (6,  [("Boughnam",           "Houda"),
          ("Amri",               "Maryam"),
          ("Khalil",             "Abderazzak")]),

    (7,  [("Khald",              "Adam"),
          ("Darraj",             "Mohamed Amine")]),

    (8,  [("Es-Saaidi",          "Youssef"),
          ("Boutrid",            "Mourad"),
          ("Zemmahi",            "Zakariae"),
          ("Kassimi",            "Achraf")]),

    (9,  [("El Hafid",           "Wiame"),
          ("Rjili",              "Houssam")]),

    (10, [("Amine",              "Faris"),
          ("Es-Safi",            "Abderrahman")]),

    (11, [("Faten",              "Saif Eddine"),
          ("Ma",                 "Bilal"),
          ("El Madani",          "Adam"),
          ("Hssaine",            "Mohammed Amine")]),

    (12, [("Nankouli",           "Marc Thierry"),
          ("Hinimdou",           "Morsia Guitdam")]),

    (13, [("Bouabdillah",        ""),      # prénom non visible
          ("Baqua",              "")]),    # prénom non visible

    # Ligne 14 IGNORÉE (doublon de ligne 17)

    (15, [("Elfilali Ech-Chafiq","Halima")]),

    (16, [("Djeri-Alassani",     "Oubenoupou"),
          ("Souleymane",         "Diallo")]),

    (17, [("Amllal",             "Amine"),
          ("Zouga",              "Mouhcine"),
          ("Akebli",             "Fatima Ezzahrae")]),

    (18, [("Chaibou",            "Saidou Abdoulaye")]),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(s):
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9]+', '.', s).strip('.')
    return s

def _make_username(prenom, nom):
    base = _clean(prenom) + '.' + _clean(nom) if prenom else _clean(nom)
    base = base.strip('.')
    username = base
    i = 2
    while User.objects.filter(username=username).exists():
        username = f"{base}{i}"
        i += 1
    return username

# ── Script principal ──────────────────────────────────────────────────────────

classe = Classe.objects.get(code_acces='K6YOIN62')
prof   = classe.professeur
MOT_DE_PASSE_TEMP = 'Soutenance2026!'

print(f"\nClasse    : {classe.nom}")
print(f"Professeur: {prof.get_full_name()}")
print(f"Inscrits actuels : {classe.inscrits.count()}\n")

nb_crees   = 0
nb_existants = 0
nb_ajoutes = 0

with transaction.atomic():
    for num_groupe, membres in GROUPES_DATA:
        for nom, prenom in membres:
            # Chercher si l'étudiant existe déjà (matching nom + prénom)
            qs = User.objects.filter(
                last_name__iexact=nom,
                role='etudiant',
            )
            if prenom:
                qs = qs.filter(first_name__iexact=prenom)

            if qs.exists():
                etudiant = qs.first()
                nb_existants += 1
                print(f"  [EXISTANT] {prenom} {nom} = {etudiant.username}")
            else:
                username = _make_username(prenom, nom)
                etudiant = User.objects.create_user(
                    username=username,
                    password=MOT_DE_PASSE_TEMP,
                    first_name=prenom.title() if prenom else '',
                    last_name=nom.title(),
                    role='etudiant',
                    cree_par=prof,
                )
                nb_crees += 1
                print(f"  [CREE]     {prenom} {nom} = {username}")

            # Inscrire dans la classe si pas déjà inscrit
            if not classe.inscrits.filter(pk=etudiant.pk).exists():
                classe.inscrits.add(etudiant)
                nb_ajoutes += 1

print(f"\n{'='*50}")
print(f"Comptes créés    : {nb_crees}")
print(f"Déjà existants   : {nb_existants}")
print(f"Ajoutés à la classe : {nb_ajoutes}")
print(f"Total inscrits maintenant : {classe.inscrits.count()}")
print(f"\nMot de passe temporaire : {MOT_DE_PASSE_TEMP}")
print("(Chaque étudiant peut le changer depuis son profil)")
