"""Donnees de demonstration pour les captures d'ecran du rapport.
Usage : .venv\\Scripts\\python.exe _demo_data.py
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'soutenanceai.settings')
django.setup()

from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from sessions_app.models import Classe, CritereNotation, PassageEtudiant, Session

# ── Professeur ──
prof, created = User.objects.get_or_create(
    username='samira.fadili',
    defaults={
        'first_name': 'Samira', 'last_name': 'Fadili',
        'email': 'samira.fadili@ensam.ma', 'role': User.ROLE_PROFESSEUR,
        'sexe': 'F',
    },
)
if created:
    prof.set_password('Demo2026!')
    prof.save()

# ── Etudiants ──
noms = [
    ('Oubenoupou', 'Djeri-Alassani'), ('Amine', 'Faris'), ('Lina', 'Berrada'),
    ('Youssef', 'El Amrani'), ('Sara', 'Bennani'), ('Mehdi', 'Ouazzani'),
]
etudiants = []
for prenom, nom in noms:
    u, created = User.objects.get_or_create(
        username=f'{prenom.lower().replace(" ", "")}.{nom.lower().replace(" ", "").replace("-", "")}',
        defaults={
            'first_name': prenom, 'last_name': nom,
            'role': User.ROLE_ETUDIANT, 'cree_par': prof,
        },
    )
    if created:
        u.set_password('Demo2026!')
        u.save()
    etudiants.append(u)

# ── Classe ──
classe, _ = Classe.objects.get_or_create(
    professeur=prof, nom='2A IATD-SI — Promotion 2026',
    defaults={'description': 'Deuxieme annee cycle ingenieur, filiere IATD-SI'},
)
classe.inscrits.add(*etudiants)

# ── Soutenance ──
session, created = Session.objects.get_or_create(
    professeur=prof, classe=classe,
    titre="Soutenance projet professionnel personnel de l'etudiant",
    defaults={
        'description': 'Presentation individuelle de 15 minutes suivie de questions.',
        'langue': 'fr', 'duree_presentation': 15, 'duree_questions': 5,
        'nb_questions_max': 3, 'rapport_obligatoire': True,
        'style_questionnement': 'mentor', 'style_notation': 'juste',
        'mode_notation_groupe': 'individuelle',
    },
)
if created:
    for i, (nom_c, coef) in enumerate([
        ("Clarte de l'expression", 1.0), ('Structure de la presentation', 2.0),
        ('Maitrise du sujet', 3.0), ('Reponses aux questions', 2.0),
    ]):
        CritereNotation.objects.create(
            session=session, nom=nom_c, coefficient=coef, ordre=i,
        )

# ── Passages planifies ──
if not session.passages.exists():
    base = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    for i, etu in enumerate(etudiants):
        p = PassageEtudiant.objects.create(
            session=session, type_groupe='monome', ordre_passage=i + 1,
            heure_prevue=base + timedelta(minutes=i * 25),
        )
        p.etudiants.add(etu)

print('Donnees de demo pretes :')
print(f'  prof      : samira.fadili (classe "{classe.nom}", code {classe.code_acces})')
print(f'  etudiants : {len(etudiants)} inscrits, {session.passages.count()} passages')
