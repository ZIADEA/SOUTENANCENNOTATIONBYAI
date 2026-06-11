"""Vues côté étudiant : dashboard, page upload, salle de présentation."""
import json
import logging
import threading
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.decorators import etudiant_required, role_required
from notation.agents import generer_questions
from notation.pipeline import noter_passage
from notation.services import (
    convertir_pptx_en_pdf,
    extraire_texte_pdf,
    extraire_texte_pptx,
)
from sessions_app.forms import UploadFichiersForm
from sessions_app.models import PassageEtudiant

logger = logging.getLogger('notation')


@role_required('etudiant')
def dashboard_etudiant(request):
    """Liste les classes et soutenances de l'etudiant avec son passage (ou non)."""
    passages = (
        PassageEtudiant.objects.filter(etudiants=request.user)
        .select_related('session')
        .order_by('heure_prevue')  # croissant : prochains d'abord
    )

    # Dictionnaire session_id -> passage (au plus 1 par session pour cet etudiant)
    passage_par_session_id = {p.session_id: p for p in passages}

    classes_qs = (
        request.user.classes_inscrites
        .prefetch_related('sessions__passages')
        .select_related('professeur')
        .order_by('-date_creation')
    )

    # Structurer : liste de (classe, [(soutenance, passage_ou_None), ...])
    classes_info = []
    for classe in classes_qs:
        sessions_info = [
            (s, passage_par_session_id.get(s.id))
            for s in classe.sessions.all().order_by('titre')
        ]
        classes_info.append((classe, sessions_info))

    return render(request, 'presentation/dashboard.html', {
        'classes_info': classes_info,
        'passages': passages,
        'has_content': bool(classes_qs),
    })


@role_required('etudiant')
def detail_passage(request, passage_id):
    passage = _get_passage_etudiant(request, passage_id)
    return render(request, 'presentation/detail_passage.html', {
        'passage': passage, 'session': passage.session,
    })


@role_required('etudiant')
@require_http_methods(['GET', 'POST'])
def upload_fichiers(request, passage_id):
    passage = _get_passage_etudiant(request, passage_id)
    form = UploadFichiersForm(request.POST or None, request.FILES or None, instance=passage)
    if request.method == 'POST' and form.is_valid():
        form.save()
        # Conversion PPTX → PDF via LibreOffice pour l'affichage PDF.js
        if passage.fichier_pptx:
            dossier = Path(settings.MEDIA_ROOT) / 'slides_pdf' / str(passage.id)
            convertir_pptx_en_pdf(passage.fichier_pptx.path, dossier)
        messages.success(request, 'Fichiers téléversés. Vous pouvez démarrer la présentation.')
        return redirect('presentation:salle', passage_id=passage.id)
    return render(request, 'presentation/upload.html', {
        'form': form, 'passage': passage,
    })


@role_required('etudiant')
def salle_presentation(request, passage_id):
    """Salle style visioconférence : slides + webcam + timer + micro."""
    passage = _get_passage_etudiant(request, passage_id)
    if passage.session.rapport_obligatoire and not passage.fichier_rapport:
        messages.error(request, "Vous devez déposer un rapport PDF avant de commencer.")
        return redirect('presentation:upload', passage_id=passage.id)
    if not passage.fichier_pptx:
        messages.error(request, "Vous devez déposer un PPTX avant de commencer.")
        return redirect('presentation:upload', passage_id=passage.id)

    # URL du PDF de slides converti depuis le PPTX
    from notation.services import convertir_pptx_en_pdf
    dossier_pdf = Path(settings.MEDIA_ROOT) / 'slides_pdf' / str(passage.id)
    pdf_url = ''
    if passage.fichier_pptx:
        pdf_path = dossier_pdf / (Path(passage.fichier_pptx.name).stem + '.pdf')
        # Relancer la conversion si le PDF est absent (ex: premier accès apres upload)
        if not pdf_path.exists():
            convertir_pptx_en_pdf(passage.fichier_pptx.path, dossier_pdf)
        if pdf_path.exists():
            rel = pdf_path.relative_to(settings.MEDIA_ROOT).as_posix()
            pdf_url = settings.MEDIA_URL + rel

    # Nom complet de l'etudiant courant pour le message d'accueil
    etudiant = request.user
    etudiant_nom = etudiant.get_full_name() or etudiant.username

    # Avatar du professeur selon son sexe
    prof = passage.session.professeur
    prof_nom = prof.get_full_name() or prof.username
    if prof.sexe == 'F':
        prof_avatar = 'img/prof_femme.jpeg'
    elif prof.sexe == 'H':
        prof_avatar = 'img/prof_homme.jpeg'
    else:
        prof_avatar = ''  # Pas d'avatar si sexe non renseigne

    return render(request, 'presentation/salle.html', {
        'passage': passage,
        'session': passage.session,
        'pdf_url': pdf_url,
        'etudiant_nom': etudiant_nom,
        'prof_nom': prof_nom,
        'prof_avatar': prof_avatar,
    })


# ============================================================================
# Endpoints AJAX appelés par le JS de la salle
# ============================================================================

@role_required('etudiant')
@require_http_methods(['POST'])
def demarrer(request, passage_id):
    passage = _get_passage_etudiant(request, passage_id)
    passage.statut = 'en_cours'
    passage.date_debut = timezone.now()
    passage.save(update_fields=['statut', 'date_debut'])
    _broadcast(passage_id, 'statut_update', {'statut': 'en_cours'})
    return JsonResponse({'ok': True})


@role_required('etudiant')
@require_http_methods(['POST'])
def terminer_presentation(request, passage_id):
    """Passage présentation → session questions. Génère les questions IA."""
    passage = _get_passage_etudiant(request, passage_id)
    passage.statut = 'questions'
    passage.save(update_fields=['statut'])

    # Génération des questions IA
    questions = []
    try:
        if settings.ANTHROPIC_API_KEY:
            contenu_slides = (
                extraire_texte_pptx(passage.fichier_pptx.path)
                if passage.fichier_pptx else ''
            )
            contenu_rapport = (
                extraire_texte_pdf(passage.fichier_rapport.path)
                if passage.fichier_rapport else ''
            )
            questions = generer_questions(
                transcription=passage.transcription,
                contenu_slides=contenu_slides,
                contenu_rapport=contenu_rapport,
                langue=passage.session.langue,
                nb_questions=passage.session.nb_questions_max,
                style_questionnement=passage.session.style_questionnement,
                consignes=passage.session.consignes_ia,
            )
    except Exception:
        logger.exception('Erreur génération questions')

    _broadcast(passage_id, 'statut_update', {'statut': 'questions', 'questions': questions})
    return JsonResponse({'ok': True, 'questions': questions})


@role_required('etudiant')
@require_http_methods(['POST'])
def terminer_passage(request, passage_id):
    """Tout est fini → on lance le pipeline de notation en arrière-plan."""
    passage = _get_passage_etudiant(request, passage_id)

    # Idempotence : si déjà terminé ou noté, répondre immédiatement sans relancer
    if passage.statut in ('termine', 'note'):
        return JsonResponse({'ok': True, 'already_done': True})

    passage.statut = 'termine'
    passage.date_fin = timezone.now()
    passage.save(update_fields=['statut', 'date_fin'])
    _broadcast(passage_id, 'statut_update', {'statut': 'termine'})

    # Lancement notation dans un thread daemon — la réponse HTTP revient immédiatement
    # pour éviter le timeout Daphne (noter_passage prend 20-30s avec les appels Claude)
    if settings.ANTHROPIC_API_KEY:
        def _noter():
            try:
                noter_passage(passage)
            except Exception:
                logger.exception('Erreur pipeline notation (passage %s)', passage_id)

        t = threading.Thread(target=_noter, daemon=True)
        t.start()

    return JsonResponse({'ok': True})


# Note : l'upload de chunks audio passe désormais par WebSocket
# (notation.consumers.AudioStreamConsumer) — pas d'endpoint HTTP ici.


@role_required('etudiant')
@csrf_exempt
@require_http_methods(['POST'])
def upload_video(request, passage_id):
    """Reçoit l'enregistrement vidéo complet en fin de soutenance."""
    passage = _get_passage_etudiant(request, passage_id)
    f = request.FILES.get('video')
    if not f:
        return JsonResponse({'ok': False, 'erreur': 'Pas de vidéo'}, status=400)
    passage.enregistrement_video.save(f.name, f)
    return JsonResponse({'ok': True})


@role_required('etudiant')
@csrf_exempt
@require_http_methods(['POST'])
def upload_posture(request, passage_id):
    """Reçoit des données MediaPipe collectées côté JS."""
    passage = _get_passage_etudiant(request, passage_id)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erreur': 'JSON invalide'}, status=400)
    data = passage.donnees_posture or {}
    serie = data.get('serie', [])
    serie.extend(payload.get('mesures', []))
    data['serie'] = serie[-5000:]  # limite mémoire : ~55h à 4s/mesure
    # Conserver le dernier résumé prosodique (Web Audio API)
    if 'prosody' in payload:
        data['prosody'] = payload['prosody']
    passage.donnees_posture = data
    passage.save(update_fields=['donnees_posture'])
    return JsonResponse({'ok': True})


@role_required('etudiant')
@csrf_exempt
@require_http_methods(['POST'])
def repondre_question(request, passage_id):
    """L'étudiant envoie sa réponse à une question."""
    from notation.agents import evaluer_reponse
    from notation.models import QuestionPosee

    passage = _get_passage_etudiant(request, passage_id)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erreur': 'JSON invalide'}, status=400)
    question_txt = payload.get('question', '').strip()
    reponse_txt = payload.get('reponse', '').strip()
    if not question_txt or not reponse_txt:
        return JsonResponse({'ok': False, 'erreur': 'Question/réponse vides'}, status=400)

    eval_ia = {'note': None, 'commentaire': ''}
    if settings.ANTHROPIC_API_KEY:
        try:
            eval_ia = evaluer_reponse(
                question_txt, reponse_txt,
                langue=passage.session.langue,
                style_questionnement=passage.session.style_questionnement,
            )
        except Exception:
            logger.exception('Erreur évaluation réponse')

    QuestionPosee.objects.create(
        passage=passage, auteur='ia', question=question_txt,
        reponse_etudiant=reponse_txt,
        evaluation_ia=eval_ia.get('commentaire', ''),
        note_reponse=eval_ia.get('note'),
    )
    return JsonResponse({'ok': True, 'evaluation': eval_ia})


# ============================================================================
# Reconnaissance faciale — photos de référence pour face-api.js
# ============================================================================

@role_required('etudiant')
def face_descriptors(request, passage_id):
    """Retourne les URLs des photos de profil des étudiants du passage.
    face-api.js les utilise côté navigateur pour construire les descripteurs faciaux
    de référence et identifier qui est devant la caméra.
    """
    passage = _get_passage_etudiant(request, passage_id)
    etudiants = []
    for etu in passage.etudiants.select_related().all():
        if etu.photo_profil:
            etudiants.append({
                'user_id': etu.id,
                'nom': etu.get_full_name() or etu.username,
                'photo_url': request.build_absolute_uri(etu.photo_profil.url),
            })
    return JsonResponse({'etudiants': etudiants, 'count': len(etudiants)})


# ============================================================================
# Helpers
# ============================================================================

def _get_passage_etudiant(request, passage_id):
    passage = get_object_or_404(PassageEtudiant, pk=passage_id)
    if not passage.etudiants.filter(id=request.user.id).exists():
        raise PermissionDenied("Ce passage ne vous est pas affecté.")
    return passage


def _broadcast(passage_id: int, event_type: str, payload: dict) -> None:
    layer = get_channel_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        f'passage_{passage_id}',
        {'type': event_type, 'payload': payload},
    )
