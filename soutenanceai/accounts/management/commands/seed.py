"""Cree des comptes de demonstration et une session exemple.

Usage : python manage.py seed
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from sessions_app.constants import CRITERES_PREDEFINIS
from sessions_app.models import CritereNotation, PassageEtudiant, Session

User = get_user_model()


class Command(BaseCommand):
    help = 'Cree des comptes de demo et une session exemple.'

    def handle(self, *args, **options):
        # Force UTF-8 pour eviter les erreurs d'encodage sur Windows
        import sys
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass

        ok = '[OK]'

        # --- Superadmin
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@soutenanceai.local',
                'first_name': 'Super', 'last_name': 'Admin',
                'is_staff': True, 'is_superuser': True,
                'role': User.ROLE_SUPERADMIN,
            },
        )
        if created:
            admin.set_password('admin123')
            admin.save()
        self.stdout.write(self.style.SUCCESS(f'{ok} Superadmin : admin / admin123'))

        # --- Professeur
        prof, created = User.objects.get_or_create(
            username='prof.martin',
            defaults={
                'email': 'martin@univ.fr', 'first_name': 'Pierre', 'last_name': 'Martin',
                'role': User.ROLE_PROFESSEUR,
            },
        )
        if created:
            prof.set_password('prof1234')
            prof.save()
        self.stdout.write(self.style.SUCCESS(f'{ok} Professeur : prof.martin / prof1234'))

        # --- Etudiants
        etudiants = []
        for username, prenom, nom in [
            ('alice.dupont', 'Alice', 'Dupont'),
            ('bob.leroy', 'Bob', 'Leroy'),
            ('clara.nguyen', 'Clara', 'Nguyen'),
        ]:
            etu, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': prenom, 'last_name': nom,
                    'email': f'{username}@univ.fr',
                    'role': User.ROLE_ETUDIANT, 'cree_par': prof,
                },
            )
            if created:
                etu.set_password('etudiant123')
                etu.save()
            self.stdout.write(self.style.SUCCESS(f'{ok} Etudiant : {username} / etudiant123'))
            etudiants.append(etu)

        # --- Session exemple
        session, created = Session.objects.get_or_create(
            titre="Soutenance projet de fin d'annee - Informatique",
            professeur=prof,
            defaults={
                'description': "Soutenance de fin d'annee - projet individuel ou en binome.",
                'langue': 'fr',
                'duree_presentation': 15,
                'duree_questions': 5,
                'nb_questions_max': 3,
                'rapport_obligatoire': True,
                'coefficient_rapport': 1.5,
                'personnalite_ia': 'neutre',
                'consignes_ia': 'Evaluation academique standard. Clarte et rigueur methodologique.',
                'mode_notation_groupe': 'individuelle',
                'coefficient_groupe': 0.5,
                'coefficient_individuel': 0.5,
            },
        )
        if created:
            for ordre, (nom, desc) in enumerate(CRITERES_PREDEFINIS[:8]):
                CritereNotation.objects.create(
                    session=session, nom=nom, description=desc,
                    coefficient=1.0, est_personnalise=False, ordre=ordre,
                )
            self.stdout.write(self.style.SUCCESS(f'{ok} Session creee : "{session.titre}"'))

            for i, etu in enumerate(etudiants[:2], start=1):
                p = PassageEtudiant.objects.create(
                    session=session, type_groupe='monome', ordre_passage=i,
                    heure_prevue=timezone.now() + timezone.timedelta(days=1, hours=i),
                )
                p.etudiants.add(etu)
            self.stdout.write(self.style.SUCCESS(f'{ok} 2 passages exemple ajoutes'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{ok} Session deja existante'))

        self.stdout.write(self.style.SUCCESS('\nDonnees de demo pretes !'))
        self.stdout.write('-----------------------------------')
        self.stdout.write('  admin        / admin123     (Superadmin)')
        self.stdout.write('  prof.martin  / prof1234     (Professeur)')
        self.stdout.write('  alice.dupont / etudiant123  (Etudiante)')
        self.stdout.write('  bob.leroy    / etudiant123  (Etudiant)')
        self.stdout.write('  clara.nguyen / etudiant123  (Etudiante)')
        self.stdout.write('-----------------------------------')
        self.stdout.write('Ouvrez http://127.0.0.1:8000')
