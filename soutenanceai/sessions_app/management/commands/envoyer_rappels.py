"""Management command : envoyer les rappels email 10 min avant chaque passage.

Usage (à appeler toutes les minutes depuis un scheduler/cron) :
    .venv\\Scripts\\python.exe manage.py envoyer_rappels

Windows Task Scheduler : toutes les minutes, commande :
    .venv\\Scripts\\python.exe manage.py envoyer_rappels
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from sessions_app.emails import envoyer_rappel_passage
from sessions_app.models import PassageEtudiant


class Command(BaseCommand):
    help = 'Envoie les rappels email aux étudiants dont le passage est dans ~10 minutes.'

    def handle(self, *args, **options):
        maintenant = timezone.now()
        # Fenêtre : passages prévus entre 9 et 11 minutes dans le futur
        debut = maintenant + timedelta(minutes=9)
        fin   = maintenant + timedelta(minutes=11)

        passages = PassageEtudiant.objects.filter(
            statut='en_attente',
            rappel_envoye=False,
            heure_prevue__gte=debut,
            heure_prevue__lte=fin,
        ).select_related('session__professeur').prefetch_related('etudiants')

        nb = passages.count()
        if nb == 0:
            self.stdout.write('Aucun rappel à envoyer.')
            return

        envoyes = 0
        for passage in passages:
            ok = envoyer_rappel_passage(passage)
            if ok:
                passage.rappel_envoye = True
                passage.save(update_fields=['rappel_envoye'])
                envoyes += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Rappel envoye — passage #{passage.ordre_passage} '
                        f'({passage.noms_etudiants}) a {passage.heure_prevue.strftime("%H:%M")}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Rappel non envoye (email manquant ?) — passage #{passage.ordre_passage}'
                    )
                )

        self.stdout.write(f'{envoyes}/{nb} rappel(s) envoye(s).')
