"""Vues notation : modification de notes par le prof, génération rapport PDF, déclenchement."""
import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.decorators import professeur_required
from sessions_app.models import PassageEtudiant

from .models import NoteIA
from .pipeline import calculer_note_globale, noter_passage
from .rapports import generer_rapport_pdf


@professeur_required
def notes_passage(request, passage_id):
    passage = get_object_or_404(
        PassageEtudiant, pk=passage_id, session__professeur=request.user,
    )
    session = passage.session
    etudiants = list(passage.etudiants.all())

    notes_par_etudiant = []
    for etu in etudiants:
        notes = list(
            NoteIA.objects.filter(passage=passage, etudiant=etu)
            .select_related('critere')
            .order_by('critere__ordre')
        )

        # ── Calcul détaillé de la formule ──────────────────────────────
        termes = []
        total_coef = 0.0
        total_pondere = 0.0
        for n in notes:
            produit = round(n.note_finale * n.critere.coefficient, 2)
            termes.append({
                'critere': n.critere.nom,
                'note_ia': n.note_ia,
                'note_finale': n.note_finale,
                'coef': n.critere.coefficient,
                'produit': produit,
                'modifiee': n.modifiee_par_prof,
            })
            total_coef += n.critere.coefficient
            total_pondere += n.note_finale * n.critere.coefficient

        globale = round(total_pondere / total_coef, 2) if total_coef else None

        # ── Source de la transcription ──────────────────────────────────
        trans_indiv = (passage.transcriptions_par_etudiant or {}).get(str(etu.id))
        source_transcription = 'individuelle' if trans_indiv else 'globale'

        # Synthèse IA globale pour cet étudiant (ton, disfluences, cohérence)
        synthese_etu = (passage.syntheses_ia or {}).get(str(etu.id), {})

        notes_par_etudiant.append({
            'etudiant': etu,
            'notes': notes,
            'globale': globale,
            'termes': termes,
            'total_coef': round(total_coef, 2),
            'total_pondere': round(total_pondere, 2),
            'source_transcription': source_transcription,
            'synthese_ia': synthese_etu,
        })

    questions = list(passage.questions_posees.all().order_by('date_posee'))

    return render(request, 'notation/notes_passage.html', {
        'passage': passage,
        'session': session,
        'notes_par_etudiant': notes_par_etudiant,
        'questions': questions,
    })


@professeur_required
@require_http_methods(['POST'])
def modifier_note(request, note_id):
    note = get_object_or_404(
        NoteIA, pk=note_id, passage__session__professeur=request.user,
    )
    nouvelle = request.POST.get('note_finale')
    commentaire = request.POST.get('commentaire_prof', '')
    try:
        note.note_finale = max(0, min(20, float(nouvelle)))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'erreur': 'Note invalide'}, status=400)
    note.commentaire_prof = commentaire
    note.modifiee_par_prof = True
    note.save()
    # Broadcast WebSocket aux observers du live
    layer = get_channel_layer()
    if layer:
        async_to_sync(layer.group_send)(
            f'passage_{note.passage_id}',
            {
                'type': 'note_update',
                'payload': {
                    'note_id': note.id,
                    'etudiant_id': note.etudiant_id,
                    'critere': note.critere.nom,
                    'note_finale': note.note_finale,
                    'commentaire_prof': note.commentaire_prof,
                    'modifiee_par_prof': True,
                },
            },
        )
    return JsonResponse({'ok': True, 'note_finale': note.note_finale})


@professeur_required
@require_http_methods(['POST'])
def declencher_notation(request, passage_id):
    """Lance le pipeline IA sur un passage (synchrone — pour un vrai prod : Celery)."""
    passage = get_object_or_404(
        PassageEtudiant, pk=passage_id, session__professeur=request.user,
    )
    resultats = noter_passage(passage)
    if resultats.get('erreurs'):
        messages.warning(request, f'Notation partielle. Erreurs : {resultats["erreurs"]}')
    else:
        messages.success(request, 'Notation IA terminée.')
    return redirect('notation:notes_passage', passage_id=passage.id)


@professeur_required
def telecharger_rapport(request, passage_id):
    passage = get_object_or_404(
        PassageEtudiant, pk=passage_id, session__professeur=request.user,
    )
    pdf_bytes = generer_rapport_pdf(passage)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="rapport_passage_{passage.id}.pdf"'
    )
    return response
