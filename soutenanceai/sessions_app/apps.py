import threading
import time
import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


def _rappels_loop():
    """Thread de fond : vérifie toutes les 60 s s'il faut envoyer des rappels."""
    # Attente initiale pour laisser Django finir son démarrage
    time.sleep(10)
    while True:
        try:
            from django.utils import timezone
            from datetime import timedelta
            from sessions_app.models import PassageEtudiant
            from sessions_app.emails import envoyer_rappel_passage

            maintenant = timezone.now()
            debut = maintenant + timedelta(minutes=9)
            fin   = maintenant + timedelta(minutes=11)

            passages = PassageEtudiant.objects.filter(
                statut='en_attente',
                rappel_envoye=False,
                heure_prevue__gte=debut,
                heure_prevue__lte=fin,
            ).select_related('session__professeur').prefetch_related('etudiants')

            for passage in passages:
                ok = envoyer_rappel_passage(passage)
                if ok:
                    passage.rappel_envoye = True
                    passage.save(update_fields=['rappel_envoye'])
                    logger.info(
                        '[rappels] Email envoyé — passage #%s à %s',
                        passage.ordre_passage,
                        passage.heure_prevue.strftime('%H:%M'),
                    )
        except Exception:
            logger.exception('[rappels] Erreur dans le thread de rappels')

        time.sleep(60)


class SessionsAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sessions_app'
    verbose_name = 'Sessions de soutenance'

    def ready(self):
        import os
        import sys

        argv = ' '.join(sys.argv).lower()
        is_runserver = 'runserver' in argv
        is_daphne = 'daphne' in argv or 'asgi' in argv

        # Commandes de gestion (migrate, test, shell...) : pas de thread
        if not (is_runserver or is_daphne):
            return
        # runserver lance 2 processus (autoreload) : ne démarrer que dans l'enfant
        if is_runserver and os.environ.get('RUN_MAIN') != 'true':
            return

        t = threading.Thread(target=_rappels_loop, daemon=True, name='rappels-email')
        t.start()
        logger.info('[rappels] Thread de rappels email démarré.')
