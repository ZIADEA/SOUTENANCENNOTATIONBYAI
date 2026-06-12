"""Endpoint de chat de l'assistant IA contextuel.

POST /assistant/chat/  {message: str, history: [{role, content}, ...]}
Accessible à tous (le contexte injecté dépend du rôle de request.user) :
visiteur anonyme, étudiant, professeur, superadmin.
"""
import json
import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .context import construire_contexte
from .knowledge import CONNAISSANCE_APPLICATION, REGLES_ASSISTANT

logger = logging.getLogger('assistant')

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_MESSAGES = 12
MAX_TOKENS_REPONSE = 700


def _system_prompt(user) -> str:
    return (
        f'{REGLES_ASSISTANT}\n\n{CONNAISSANCE_APPLICATION}\n\n'
        f'# Données de l\'utilisateur (NE JAMAIS révéler celles d\'autrui)\n'
        f'{construire_contexte(user)}'
    )


@require_http_methods(['POST'])
def chat(request):
    if not settings.ANTHROPIC_API_KEY:
        return JsonResponse(
            {'erreur': 'assistant_indisponible'}, status=503,
        )

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'erreur': 'json_invalide'}, status=400)

    message = (payload.get('message') or '').strip()[:MAX_MESSAGE_CHARS]
    if not message:
        return JsonResponse({'erreur': 'message_vide'}, status=400)

    # Historique côté client : on ne garde que les derniers échanges valides
    history = payload.get('history') or []
    messages = []
    for h in history[-MAX_HISTORY_MESSAGES:]:
        role = h.get('role')
        content = (h.get('content') or '').strip()[:MAX_MESSAGE_CHARS]
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': message})

    from notation.agents import get_client

    try:
        response = get_client().messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=MAX_TOKENS_REPONSE,
            system=_system_prompt(request.user),
            messages=messages,
        )
        texte = response.content[0].text.strip()
        # Le widget affiche en texte brut : on retire le markdown résiduel
        texte = re.sub(r'^#{1,6}\s*', '', texte, flags=re.MULTILINE)
        texte = texte.replace('**', '')
    except Exception:
        logger.exception('Erreur assistant IA')
        return JsonResponse({'erreur': 'erreur_ia'}, status=502)

    return JsonResponse({'reponse': texte})
