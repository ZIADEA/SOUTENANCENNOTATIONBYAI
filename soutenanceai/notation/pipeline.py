"""Pipeline complet : à partir d'un PassageEtudiant terminé, lance la notation."""
from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from sessions_app.models import PassageEtudiant

from .agents import ContexteNotation, Orchestrateur, evaluer_demo_video, evaluer_depot_github
from .models import NoteIA, QuestionPosee
from .services import (
    enrichir_posture_avec_prosody,
    extraire_frames_video,
    extraire_texte_pdf,
    extraire_texte_pptx,
    fetch_github_repo,
    resumer_posture,
)

logger = logging.getLogger('notation')


# ============================================================================
# Résolution de la transcription par étudiant
# ============================================================================

def _resoudre_transcription(passage: PassageEtudiant, etudiant) -> str:
    """Retourne la transcription individuelle de l'étudiant si disponible
    (chaque étudiant a présenté depuis son propre appareil), sinon la
    transcription globale du passage.
    """
    trans_indiv = (passage.transcriptions_par_etudiant or {}).get(str(etudiant.id))
    if trans_indiv:
        logger.info(
            'Transcription individuelle pour %s (%d chars)',
            etudiant.get_full_name() or etudiant.username, len(trans_indiv),
        )
        return trans_indiv
    logger.info(
        'Transcription globale utilisee pour %s (pas de transcription individuelle)',
        etudiant.get_full_name() or etudiant.username,
    )
    return passage.transcription


# ============================================================================
# Pipeline principal
# ============================================================================

def noter_passage(passage: PassageEtudiant) -> dict:
    """Pipeline complet :
    1. Extrait slides + rapport
    2. Récupère transcription + données posture
    3. Pour chaque étudiant du passage : appelle Claude (orchestrateur)
    4. Sauvegarde les notes en BDD
    Retourne un résumé.
    """
    session = passage.session

    contenu_slides = ''
    contenu_rapport = ''
    if passage.fichier_pptx:
        contenu_slides = extraire_texte_pptx(passage.fichier_pptx.path)
    if passage.fichier_rapport:
        contenu_rapport = extraire_texte_pdf(passage.fichier_rapport.path)

    raw_posture = passage.donnees_posture or {}
    posture_raw = raw_posture.get('serie', [])
    prosody_raw = raw_posture.get('prosody', {})

    if posture_raw or prosody_raw:
        # Données brutes présentes → calculer le résumé et sauvegarder (première notation)
        posture = resumer_posture(posture_raw) if posture_raw else {}
        if prosody_raw:
            posture = enrichir_posture_avec_prosody(posture, prosody_raw)
        passage.donnees_posture = posture
        passage.save(update_fields=['donnees_posture'])
    elif 'pourcentage_contact_visuel' in raw_posture or 'ratio_silence_pct' in raw_posture:
        # Résumé déjà calculé (re-notation) → réutiliser directement
        posture = raw_posture
    else:
        posture = {}

    duree_reelle = 0.0
    if passage.date_debut and passage.date_fin:
        duree_reelle = (passage.date_fin - passage.date_debut).total_seconds() / 60

    # Débit de parole estimé (mots/min) — calculé depuis transcription + durée réelle
    if passage.transcription and duree_reelle > 0:
        nb_mots = len(passage.transcription.split())
        posture['debit_mots_par_min'] = round(nb_mots / duree_reelle, 1)
        logger.info('Debit estime : %s mots/min (%d mots / %.1f min)',
                    posture['debit_mots_par_min'], nb_mots, duree_reelle)

    # Récupérer les questions-réponses posées pendant la session
    questions_reponses = [
        {'question': q.question, 'reponse': q.reponse_etudiant or ''}
        for q in QuestionPosee.objects.filter(passage=passage, auteur='ia').order_by('id')
        if q.question
    ]
    logger.info('Questions-reponses : %d entrees pour passage %s', len(questions_reponses), passage.id)

    criteres = list(session.criteres.all().order_by('ordre'))
    criteres_data = [
        {'nom': c.nom, 'coefficient': c.coefficient, 'description': c.description}
        for c in criteres
    ]
    etudiants = list(passage.etudiants.all())
    if not etudiants:
        return {'erreur': 'Aucun étudiant associé au passage'}

    orchestrateur = Orchestrateur(
        style_questionnement=session.style_questionnement,
        style_notation=session.style_notation,
        ajustement_auto=session.ajustement_auto_stress,
    )
    membres_noms = [e.get_full_name() or e.username for e in etudiants]

    # Kwargs communs à tous les ContexteNotation
    _ctx_base = dict(
        contenu_slides=contenu_slides,
        contenu_rapport=contenu_rapport,
        criteres=criteres_data,
        langue=session.langue,
        duree_prevue_min=session.duree_presentation,
        duree_reelle_min=duree_reelle,
        donnees_posture=posture,
        style_questionnement=session.style_questionnement,
        style_notation=session.style_notation,
        type_groupe=passage.type_groupe,
        membres_groupe=membres_noms,
        questions_reponses=questions_reponses,
    )

    resultats = {'notes_par_etudiant': {}, 'erreurs': []}

    # ── Mode identique : une seule évaluation, note copiée pour tout le monde ──
    if session.mode_notation_groupe == 'identique':
        ctx = ContexteNotation(
            **_ctx_base,
            transcription=passage.transcription,   # globale par définition
            nom_etudiant=', '.join(membres_noms),
            consignes_prof=session.consignes_ia,
        )
        reponse_ia = orchestrateur.noter(ctx)
        if 'erreur' in reponse_ia:
            resultats['erreurs'].append(reponse_ia['erreur'])
            return resultats
        for etu in etudiants:
            _sauver_notes(passage, etu, criteres, reponse_ia)
            resultats['notes_par_etudiant'][etu.id] = reponse_ia

    # ── Mode mixte : collectif + individuel → combinaison pondérée ──
    elif session.mode_notation_groupe == 'mixte':
        logger.info(
            'Notation mixte — passage %s : coef_groupe=%.2f coef_individuel=%.2f',
            passage.id, session.coefficient_groupe, session.coefficient_individuel,
        )

        # 1. Évaluation collective (le groupe en entier)
        consignes_collective = (
            "EVALUATION COLLECTIVE : note la performance globale du groupe en tant "
            "qu'entite. Ignore les contributions individuelles et evalue l'ensemble.\n\n"
            + (session.consignes_ia or '')
        )
        ctx_collectif = ContexteNotation(
            **_ctx_base,
            transcription=passage.transcription,
            nom_etudiant=', '.join(membres_noms),
            consignes_prof=consignes_collective,
        )
        reponse_collective = orchestrateur.noter(ctx_collectif)
        if 'erreur' in reponse_collective:
            resultats['erreurs'].append(
                f'Evaluation collective : {reponse_collective["erreur"]}'
            )
            return resultats
        logger.info('Notation mixte — evaluation collective OK')

        # 2. Évaluation individuelle + combinaison pour chaque étudiant
        for etu in etudiants:
            nom_etu = etu.get_full_name() or etu.username
            transcription_etu = _resoudre_transcription(passage, etu)
            consignes_individuelle = (
                f"EVALUATION INDIVIDUELLE : evalue specifiquement la contribution "
                f"de {nom_etu} au sein du groupe. Concentre-toi sur ce qu'il/elle "
                f"a apporte personnellement (prise de parole, maitrise, reponses).\n\n"
                + (session.consignes_ia or '')
            )
            ctx_indiv = ContexteNotation(
                **_ctx_base,
                transcription=transcription_etu,
                nom_etudiant=nom_etu,
                consignes_prof=consignes_individuelle,
            )
            reponse_individuelle = orchestrateur.noter(ctx_indiv)
            if 'erreur' in reponse_individuelle:
                resultats['erreurs'].append(
                    f'{nom_etu} (individuel) : {reponse_individuelle["erreur"]}'
                )
                continue

            _sauver_notes_mixtes(
                passage, etu, criteres,
                reponse_collective, reponse_individuelle,
                session.coefficient_groupe, session.coefficient_individuel,
            )
            resultats['notes_par_etudiant'][etu.id] = {
                'collectif': reponse_collective,
                'individuel': reponse_individuelle,
            }
            logger.info('Notation mixte — %s OK', nom_etu)

    # ── Mode individuelle : un appel IA par étudiant avec SA transcription ──
    else:
        for etu in etudiants:
            nom_etu = etu.get_full_name() or etu.username
            transcription_etu = _resoudre_transcription(passage, etu)
            ctx = ContexteNotation(
                **_ctx_base,
                transcription=transcription_etu,
                nom_etudiant=nom_etu,
                consignes_prof=session.consignes_ia,
            )
            reponse_ia = orchestrateur.noter(ctx)
            if 'erreur' in reponse_ia:
                resultats['erreurs'].append(f'{nom_etu}: {reponse_ia["erreur"]}')
                continue
            _sauver_notes(passage, etu, criteres, reponse_ia)
            resultats['notes_par_etudiant'][etu.id] = reponse_ia

    passage.statut = 'note'
    passage.save(update_fields=['statut'])

    # Notifier le prof si tous les passages de la session sont maintenant notés
    try:
        from sessions_app.emails import envoyer_notification_session_terminee
        tous_termines = not passage.session.passages.exclude(statut='note').exists()
        if tous_termines:
            envoyer_notification_session_terminee(passage.session)
            logger.info('Email session terminee envoye — session %s', passage.session.id)
    except Exception:
        logger.exception('Erreur envoi email session terminee')

    # ── Analyse vidéo de démonstration (optionnelle) ──────────────────────────
    if session.demo_video_requise and passage.fichier_demo_video:
        try:
            logger.info('Analyse vidéo démo — passage %s', passage.id)
            frames = extraire_frames_video(passage.fichier_demo_video.path, n_frames=12)
            if frames:
                resultat_video = evaluer_demo_video(
                    frames,
                    instructions=session.demo_video_instructions,
                    langue=session.langue,
                )
            else:
                resultat_video = {
                    'note': 0, 'commentaire': 'Extraction des frames impossible.',
                    'points_forts': [], 'points_faibles': [],
                }
            analyses = passage.analyses_extra or {}
            analyses['demo_video'] = resultat_video
            passage.analyses_extra = analyses
            passage.save(update_fields=['analyses_extra'])
            resultats['demo_video'] = resultat_video
            logger.info('Analyse vidéo OK — note %.1f', resultat_video.get('note', 0))
        except Exception:
            logger.exception('Erreur analyse vidéo démo — passage %s', passage.id)

    # ── Analyse dépôt GitHub (optionnel) ─────────────────────────────────────
    if session.depot_github_requis and passage.url_depot_github:
        try:
            logger.info('Analyse GitHub — %s', passage.url_depot_github)
            repo_data = fetch_github_repo(passage.url_depot_github)
            resultat_github = evaluer_depot_github(
                repo_data,
                criteres=session.criteres_github,
                langue=session.langue,
            )
            analyses = passage.analyses_extra or {}
            analyses['github'] = {**resultat_github, 'url': passage.url_depot_github}
            passage.analyses_extra = analyses
            passage.save(update_fields=['analyses_extra'])
            resultats['github'] = resultat_github
            logger.info('Analyse GitHub OK — note %.1f', resultat_github.get('note', 0))
        except Exception:
            logger.exception('Erreur analyse GitHub — passage %s', passage.id)

    return resultats


# ============================================================================
# Helpers de sauvegarde
# ============================================================================

def _sauver_notes(passage, etudiant, criteres, reponse_ia: dict) -> None:
    """Sauvegarde les notes retournées par l'IA en BDD (modes identique et individuelle).
    Sauvegarde aussi la synthèse IA (ton, disfluences, cohérence) dans PassageEtudiant.
    """
    notes_par_nom = {n['critere']: n for n in reponse_ia.get('notes', [])}
    with transaction.atomic():
        for critere in criteres:
            entry = notes_par_nom.get(critere.nom, {})
            note = float(entry.get('note', 10))
            commentaire = entry.get('commentaire', '')
            NoteIA.objects.update_or_create(
                passage=passage, etudiant=etudiant, critere=critere,
                defaults={
                    'note_ia': note,
                    'note_finale': note,
                    'commentaire_ia': commentaire,
                    'modifiee_par_prof': False,
                },
            )
        # Sauvegarder la synthèse globale de l'IA pour cet étudiant
        _sauver_synthese(passage, etudiant, reponse_ia)


def _sauver_notes_mixtes(
    passage, etudiant, criteres,
    reponse_collective: dict, reponse_individuelle: dict,
    coef_groupe: float, coef_individuel: float,
) -> None:
    """Mode mixte : note finale = (coef_groupe * note_collective + coef_individuel * note_individuelle)
    / (coef_groupe + coef_individuel).
    Les coefficients sont normalisés pour que leur somme vaille toujours 1.
    """
    notes_coll  = {n['critere']: n for n in reponse_collective.get('notes', [])}
    notes_indiv = {n['critere']: n for n in reponse_individuelle.get('notes', [])}

    total = coef_groupe + coef_individuel
    if total <= 0:
        coef_groupe, coef_individuel, total = 0.5, 0.5, 1.0

    with transaction.atomic():
        for critere in criteres:
            note_coll  = float(notes_coll.get(critere.nom,  {}).get('note', 10))
            note_indiv = float(notes_indiv.get(critere.nom, {}).get('note', 10))

            note_mixte = round(
                (coef_groupe * note_coll + coef_individuel * note_indiv) / total,
                2,
            )

            comment_coll  = notes_coll.get(critere.nom,  {}).get('commentaire', '')
            comment_indiv = notes_indiv.get(critere.nom, {}).get('commentaire', '')
            pct_g = round(100 * coef_groupe / total)
            pct_i = round(100 * coef_individuel / total)
            commentaire = (
                f"[Groupe {pct_g}%] {comment_coll}\n"
                f"[Individuel {pct_i}%] {comment_indiv}"
            ).strip()

            NoteIA.objects.update_or_create(
                passage=passage, etudiant=etudiant, critere=critere,
                defaults={
                    'note_ia': note_mixte,
                    'note_finale': note_mixte,
                    'commentaire_ia': commentaire,
                    'modifiee_par_prof': False,
                },
            )
        # Combiner les synthèses collective + individuelle
        synthese_combinee = {
            'synthese': (
                f"[Collectif] {reponse_collective.get('synthese', '')}\n"
                f"[Individuel] {reponse_individuelle.get('synthese', '')}"
            ).strip(),
            'ton_detecte': reponse_individuelle.get('ton_detecte', ''),
            'disfluences_detectees': reponse_individuelle.get('disfluences_detectees', ''),
            'coherence_corps_discours': reponse_individuelle.get('coherence_corps_discours', ''),
        }
        _sauver_synthese(passage, etudiant, synthese_combinee)


def _sauver_synthese(passage: PassageEtudiant, etudiant, reponse_ia: dict) -> None:
    """Sauvegarde la synthèse globale IA (ton, disfluences, cohérence) dans PassageEtudiant.
    Structure : passage.syntheses_ia[str(etudiant.id)] = {...}
    Utilise select_for_update() pour éviter les race conditions en mode groupe.
    """
    champs = {
        'synthese': reponse_ia.get('synthese', ''),
        'ton_detecte': reponse_ia.get('ton_detecte', ''),
        'disfluences_detectees': reponse_ia.get('disfluences_detectees', ''),
        'coherence_corps_discours': reponse_ia.get('coherence_corps_discours', ''),
    }
    with transaction.atomic():
        p = PassageEtudiant.objects.select_for_update().get(pk=passage.pk)
        syntheses = p.syntheses_ia or {}
        syntheses[str(etudiant.id)] = champs
        p.syntheses_ia = syntheses
        p.save(update_fields=['syntheses_ia'])


def calculer_note_globale(passage: PassageEtudiant, etudiant) -> Optional[float]:
    """Moyenne pondérée par coefficient des notes finales d'un étudiant."""
    notes = NoteIA.objects.filter(passage=passage, etudiant=etudiant).select_related('critere')
    if not notes.exists():
        return None
    total_pondere = 0.0
    total_coef = 0.0
    for n in notes:
        total_pondere += n.note_finale * n.critere.coefficient
        total_coef += n.critere.coefficient
    return round(total_pondere / total_coef, 2) if total_coef else None
