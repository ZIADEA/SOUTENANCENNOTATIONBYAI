"""Fonctions d'envoi d'emails pour SoutenanceAI."""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger('notation')

SITE_NAME = 'SoutenanceAI'


def _send(subject: str, body: str, recipient: str) -> bool:
    """Wrapper autour de send_mail — retourne True si envoi OK."""
    if not settings.EMAIL_HOST_USER:
        logger.warning('[email] EMAIL_HOST_USER non configuré — email non envoyé.')
        return False
    if not recipient:
        logger.warning('[email] Destinataire vide — email non envoyé.')
        return False
    try:
        send_mail(
            subject=f'[{SITE_NAME}] {subject}',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        logger.info('[email] Envoyé à %s — sujet : %s', recipient, subject)
        return True
    except Exception:
        logger.exception('[email] Echec envoi à %s — sujet : %s', recipient, subject)
        return False


# ─────────────────────────────────────────────────────────────
# Email 1 : rappel 10 min avant le passage (étudiant)
# ─────────────────────────────────────────────────────────────

def envoyer_rappel_passage(passage) -> bool:
    """Envoie un rappel à chaque étudiant du passage, 10 min avant l'heure prévue."""
    session = passage.session
    noms = passage.noms_etudiants
    heure = passage.heure_prevue.strftime('%H:%M') if passage.heure_prevue else 'non définie'

    succes = False
    for etudiant in passage.etudiants.all():
        if not etudiant.email:
            continue
        prenom = etudiant.first_name or etudiant.username
        sujet = f'Rappel — votre passage commence dans 10 minutes ({session.titre})'
        corps = (
            f'Bonjour {prenom},\n\n'
            f'Votre passage pour la soutenance « {session.titre} » est prévu à {heure}.\n'
            f'Il commence dans environ 10 minutes. Merci de vous préparer.\n\n'
            f'Durée de présentation : {session.duree_presentation} min\n'
            f'Durée des questions : {session.duree_questions} min\n\n'
            f'Connectez-vous dès maintenant sur {SITE_NAME} pour accéder à votre salle.\n\n'
            f'Bonne chance !\n'
            f'— L\'équipe {SITE_NAME}'
        )
        if _send(sujet, corps, etudiant.email):
            succes = True

    return succes


# ─────────────────────────────────────────────────────────────
# Email 2 : tous les étudiants ont passé (professeur)
# ─────────────────────────────────────────────────────────────

def envoyer_notification_session_terminee(session) -> bool:
    """Envoie un email au professeur quand tous les passages de la session sont notés."""
    prof = session.professeur
    if not prof.email:
        logger.warning('[email] Prof %s sans email — notification session ignorée.', prof.username)
        return False

    passages = session.passages.all()
    nb_total = passages.count()
    nb_notes = passages.filter(statut='note').count()
    prenom_prof = prof.first_name or prof.username

    sujet = f'Session terminée — tous les passages sont notés ({session.titre})'
    corps = (
        f'Bonjour {prenom_prof},\n\n'
        f'Tous les étudiants de la session « {session.titre} » ont effectué leur passage.\n\n'
        f'Bilan :\n'
        f'  - Passages planifiés : {nb_total}\n'
        f'  - Passages notés par l\'IA : {nb_notes}\n\n'
        f'Connectez-vous sur {SITE_NAME} pour consulter et valider les notes.\n\n'
        f'— L\'équipe {SITE_NAME}'
    )
    return _send(sujet, corps, prof.email)
