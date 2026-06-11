"""WebSocket consumers : le prof reçoit les notes en temps réel,
l'étudiant streame ses chunks audio."""
import json
import logging
from pathlib import Path

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('notation')


# ============================================================================
# LivePassageConsumer : le prof (et l'étudiant) écoutent les évènements du live
# ============================================================================

class LivePassageConsumer(AsyncJsonWebsocketConsumer):
    """Canal qui diffuse les évènements liés à un passage :
    - statut (en_cours / questions / terminé)
    - nouvelles notes IA
    - notes modifiées par le prof
    - chunks de transcription en direct
    """

    async def connect(self):
        self.passage_id = self.scope['url_route']['kwargs']['passage_id']
        self.group_name = f'passage_{self.passage_id}'
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        autorise = await self._verifier_acces(user, self.passage_id)
        if not autorise:
            await self.close(code=4003)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'connected', 'passage_id': self.passage_id})

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        type_ = content.get('type')
        if type_ == 'question_prof':
            await self.channel_layer.group_send(self.group_name, {
                'type': 'question_prof',
                'payload': {'question': content.get('question', '')},
            })

    # ----- Handlers de groupe -----------------------------------------
    async def note_update(self, event):
        await self.send_json({'type': 'note_update', 'payload': event['payload']})

    async def statut_update(self, event):
        await self.send_json({'type': 'statut_update', 'payload': event['payload']})

    async def nouvelle_note(self, event):
        await self.send_json({'type': 'nouvelle_note', 'payload': event['payload']})

    async def question_prof(self, event):
        await self.send_json({'type': 'question_prof', 'payload': event['payload']})

    async def question_ia(self, event):
        await self.send_json({'type': 'question_ia', 'payload': event['payload']})

    async def transcription_chunk(self, event):
        await self.send_json({'type': 'transcription_chunk', 'payload': event['payload']})

    async def etudiant_connecte(self, event):
        await self.send_json({'type': 'etudiant_connecte', 'payload': event['payload']})

    # ----- Helpers ---------------------------------------------------
    @database_sync_to_async
    def _verifier_acces(self, user, passage_id):
        from sessions_app.models import PassageEtudiant
        try:
            p = PassageEtudiant.objects.select_related('session').get(pk=passage_id)
        except PassageEtudiant.DoesNotExist:
            return False
        if user.is_superuser or user.role == 'superadmin':
            return True
        if p.session.professeur_id == user.id:
            return True
        if p.etudiants.filter(id=user.id).exists():
            return True
        return False


# ============================================================================
# AudioStreamConsumer : l'étudiant pousse ses chunks audio en binaire
# Chaque chunk → sauvegarde disque → Whisper (Groq) → transcription
# La transcription est broadcastée sur le groupe passage_{id}
# (donc le prof la voit défiler via LivePassageConsumer)
# ============================================================================

class AudioStreamConsumer(AsyncWebsocketConsumer):
    """WebSocket binaire : reçoit des chunks audio webm/opus de ~30 s,
    les transcrit via Groq Whisper et diffuse le texte au groupe du passage.

    Supporte aussi les trames texte JSON pour :
    - face_event : identification faciale depuis face-api.js côté navigateur
    """

    async def connect(self):
        self.passage_id = self.scope['url_route']['kwargs']['passage_id']
        self.group_name = f'passage_{self.passage_id}'
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        infos = await self._verifier_acces_et_charger(user, self.passage_id)
        if infos is None:
            await self.close(code=4003)
            return

        self.langue = infos['langue']
        self.user_id = user.id          # ← identifiant de l'étudiant connecté
        self.user_nom = user.get_full_name() or user.username
        self.chunk_counter = 0

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'audio_ready', 'passage_id': self.passage_id,
        }))

        # Signaler aux autres (prof, autres étudiants) que cet étudiant est connecté
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'etudiant_connecte',
                'payload': {'user_id': self.user_id, 'nom': self.user_nom},
            },
        )
        logger.info('AudioStreamConsumer: %s (id=%s) connecté au passage %s',
                    self.user_nom, self.user_id, self.passage_id)

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """
        - bytes_data : chunk audio binaire (~30 s) → Whisper → transcription
        - text_data  : JSON → face_event (identif. faciale depuis face-api.js)
        """
        # ── Trame texte JSON ───────────────────────────────────────────
        if text_data:
            try:
                data = json.loads(text_data)
                event_type = data.get('type')
                if event_type == 'face_event':
                    await self._handle_face_event(data)
            except (json.JSONDecodeError, Exception):
                pass
            return

        # ── Trame binaire audio ────────────────────────────────────────
        if bytes_data is None or len(bytes_data) == 0:
            return

        self.chunk_counter += 1
        n = self.chunk_counter

        # 1. Sauvegarde du chunk sur disque
        try:
            chemin = await self._sauver_chunk(self.passage_id, n, bytes_data)
        except Exception:
            logger.exception('Erreur sauvegarde chunk audio')
            await self.send(text_data=json.dumps({
                'type': 'audio_error', 'chunk': n, 'erreur': 'sauvegarde',
            }))
            return

        # 2. Transcription via Groq Whisper
        try:
            texte = await self._transcrire(chemin, self.langue)
        except Exception:
            logger.exception('Erreur transcription chunk')
            texte = ''

        if not texte:
            await self.send(text_data=json.dumps({
                'type': 'audio_ack', 'chunk': n, 'transcrit': False,
            }))
            return

        # 3a. Append à la transcription globale cumulée du passage
        await self._append_transcription(self.passage_id, texte)

        # 3b. Append à la transcription individuelle de CET étudiant
        await self._append_transcription_etudiant(self.passage_id, self.user_id, texte)

        # 4. Broadcast au groupe (le prof + tous les observers reçoivent)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'transcription_chunk',
                'payload': {'texte': texte, 'chunk': n, 'user_id': self.user_id, 'nom': self.user_nom},
            },
        )

        # 5. Accusé direct à l'étudiant qui a poussé le chunk
        await self.send(text_data=json.dumps({
            'type': 'audio_ack', 'chunk': n, 'transcrit': True, 'texte': texte,
        }))

    # ----- Handler de groupe : éviter une erreur si on reçoit notre propre broadcast
    async def transcription_chunk(self, event):
        pass

    async def etudiant_connecte(self, event): pass
    async def note_update(self, event): pass
    async def statut_update(self, event): pass
    async def nouvelle_note(self, event): pass
    async def question_prof(self, event): pass
    async def question_ia(self, event): pass

    # ----- Helpers BDD / I/O ---------------------------------------
    @database_sync_to_async
    def _verifier_acces_et_charger(self, user, passage_id):
        from sessions_app.models import PassageEtudiant
        try:
            p = PassageEtudiant.objects.select_related('session').get(pk=passage_id)
        except PassageEtudiant.DoesNotExist:
            return None
        # Étudiant affecté OU prof du passage OU superadmin
        if not p.etudiants.filter(id=user.id).exists():
            if not (user.is_superuser or p.session.professeur_id == user.id):
                return None
        return {'langue': p.session.langue}

    @database_sync_to_async
    def _sauver_chunk(self, passage_id, n, data):
        dossier = Path(settings.MEDIA_ROOT) / 'audio_chunks' / str(passage_id)
        dossier.mkdir(parents=True, exist_ok=True)
        nom = f'chunk_{timezone.now().strftime("%H%M%S")}_{n:04d}.webm'
        chemin = dossier / nom
        with chemin.open('wb') as f:
            f.write(data)
        return str(chemin)

    @database_sync_to_async
    def _transcrire(self, chemin, langue):
        from notation.services import transcrire_audio
        return transcrire_audio(chemin, langue=langue)

    @database_sync_to_async
    def _append_transcription(self, passage_id, texte):
        """Transcription globale (tous étudiants confondus) — conservée pour compatibilité."""
        from sessions_app.models import PassageEtudiant
        p = PassageEtudiant.objects.get(pk=passage_id)
        p.transcription = ((p.transcription or '') + ' ' + texte).strip()
        p.save(update_fields=['transcription'])

    @database_sync_to_async
    def _append_transcription_etudiant(self, passage_id, user_id, texte):
        """Transcription individuelle par étudiant (multi-appareil)."""
        from django.db import transaction
        from sessions_app.models import PassageEtudiant
        with transaction.atomic():
            p = PassageEtudiant.objects.select_for_update().get(pk=passage_id)
            trans = p.transcriptions_par_etudiant or {}
            key = str(user_id)
            trans[key] = ((trans.get(key) or '') + ' ' + texte).strip()
            p.transcriptions_par_etudiant = trans
            p.save(update_fields=['transcriptions_par_etudiant'])

    async def _handle_face_event(self, data: dict) -> None:
        """Traite un événement d'identification faciale envoyé par face-api.js."""
        user_id = data.get('user_id')
        nom = data.get('nom', '?')
        confidence = data.get('confidence', 0)
        logger.info(
            'face_event passage=%s : visage detecte user_id=%s nom=%s confidence=%.2f',
            self.passage_id, user_id, nom, confidence,
        )
        # Broadcast au groupe pour que le prof voie qui parle
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'etudiant_connecte',
                'payload': {
                    'user_id': user_id,
                    'nom': nom,
                    'source': 'face',
                    'confidence': confidence,
                },
            },
        )
