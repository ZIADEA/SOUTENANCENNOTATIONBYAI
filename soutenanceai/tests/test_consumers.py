"""Tests des WebSocket consumers : LivePassageConsumer et AudioStreamConsumer."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.urls import re_path

from notation.consumers import AudioStreamConsumer, LivePassageConsumer


# ============================================================================
# Middleware d'injection d'utilisateur pour les tests WS
# ============================================================================

def make_ws_app_with_user(consumer_class, user=None):
    """Crée une application ASGI qui injecte l'utilisateur dans le scope.

    Le consumer est enveloppé dans un URLRouter pour que scope['url_route']
    (et donc kwargs['passage_id']) soit renseigné comme en production.
    """
    router = URLRouter([
        re_path(r'^ws/passage/(?P<passage_id>\d+)/(?:audio/)?$', consumer_class.as_asgi()),
    ])

    async def auth_inject(scope, receive, send):
        if user is not None:
            scope['user'] = user
        await router(scope, receive, send)

    return auth_inject


def ws_app(consumer_class, user=None):
    return make_ws_app_with_user(consumer_class, user)


# ============================================================================
# LivePassageConsumer — connexion
# ============================================================================

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLivePassageConsumerConnect:

    async def test_unauthenticated_connection_closed(self):
        """Sans utilisateur → fermeture avec code 4001."""
        from unittest.mock import MagicMock
        anon = MagicMock()
        anon.is_authenticated = False

        app = ws_app(LivePassageConsumer, user=anon)
        communicator = WebsocketCommunicator(app, '/ws/passage/1/')
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4001
        await communicator.disconnect()

    async def test_no_user_in_scope_closes(self):
        """Scope sans user → fermeture 4001."""
        app = ws_app(LivePassageConsumer, user=None)
        communicator = WebsocketCommunicator(app, '/ws/passage/1/')
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4001
        await communicator.disconnect()

    async def test_authorized_user_connects(self, passage_obj, prof_user):
        """Le prof du passage peut se connecter."""
        app = ws_app(LivePassageConsumer, user=prof_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        connected, _ = await communicator.connect()
        assert connected

        # Doit recevoir le message "connected"
        response = await communicator.receive_json_from()
        assert response['type'] == 'connected'
        assert str(response['passage_id']) == str(passage_obj.pk)

        await communicator.disconnect()

    async def test_etudiant_du_passage_connects(self, passage_obj, etudiant_user):
        """L'étudiant affecté au passage peut se connecter."""
        app = ws_app(LivePassageConsumer, user=etudiant_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        connected, _ = await communicator.connect()
        assert connected

        response = await communicator.receive_json_from()
        assert response['type'] == 'connected'

        await communicator.disconnect()

    async def test_unauthorized_user_closes_4003(self, passage_obj, prof_user2):
        """Un autre prof ne peut pas accéder au passage."""
        app = ws_app(LivePassageConsumer, user=prof_user2)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4003
        await communicator.disconnect()

    async def test_superadmin_can_connect_to_any_passage(self, passage_obj, admin_user):
        """Le superadmin peut accéder à n'importe quel passage."""
        app = ws_app(LivePassageConsumer, user=admin_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_json_from()  # connected msg
        await communicator.disconnect()


# ============================================================================
# LivePassageConsumer — envoi d'événements de groupe
# ============================================================================

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLivePassageConsumerEvents:

    async def test_receives_statut_update_event(self, passage_obj, prof_user):
        app = ws_app(LivePassageConsumer, user=prof_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        await communicator.connect()
        await communicator.receive_json_from()  # connected msg

        # Simule un événement de groupe (statut_update)
        from channels.layers import get_channel_layer
        from asgiref.sync import sync_to_async

        layer = get_channel_layer()
        await layer.group_send(
            f'passage_{passage_obj.pk}',
            {'type': 'statut_update', 'payload': {'statut': 'en_cours'}},
        )
        response = await communicator.receive_json_from(timeout=3)
        assert response['type'] == 'statut_update'
        assert response['payload']['statut'] == 'en_cours'

        await communicator.disconnect()

    async def test_receives_note_update_event(self, passage_obj, prof_user):
        app = ws_app(LivePassageConsumer, user=prof_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        await communicator.connect()
        await communicator.receive_json_from()  # connected msg

        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        payload = {'note_id': 1, 'etudiant_id': 1, 'note_finale': 15.0}
        await layer.group_send(
            f'passage_{passage_obj.pk}',
            {'type': 'note_update', 'payload': payload},
        )
        response = await communicator.receive_json_from(timeout=3)
        assert response['type'] == 'note_update'
        assert response['payload']['note_finale'] == 15.0

        await communicator.disconnect()

    async def test_prof_question_forwarded_to_group(self, passage_obj, prof_user):
        """Un message question_prof envoyé par le client est forwardé au groupe."""
        app = ws_app(LivePassageConsumer, user=prof_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        await communicator.connect()
        await communicator.receive_json_from()  # connected

        # Le prof envoie une question
        await communicator.send_json_to({
            'type': 'question_prof',
            'question': 'Quelle est la complexité de votre algorithme ?',
        })

        # Le message doit être reçu en retour (le prof est dans le groupe)
        response = await communicator.receive_json_from(timeout=3)
        assert response['type'] == 'question_prof'
        assert 'complexité' in response['payload']['question']

        await communicator.disconnect()

    async def test_disconnect_removes_from_group(self, passage_obj, prof_user):
        """Après disconnect, le consumer ne reçoit plus les messages du groupe."""
        app = ws_app(LivePassageConsumer, user=prof_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/')
        await communicator.connect()
        await communicator.receive_json_from()
        await communicator.disconnect()

        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        # Ce send ne doit pas bloquer ni lever d'exception
        await layer.group_send(
            f'passage_{passage_obj.pk}',
            {'type': 'statut_update', 'payload': {'statut': 'termine'}},
        )
        # Pas d'exception = succès


# ============================================================================
# AudioStreamConsumer — connexion
# ============================================================================

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAudioStreamConsumerConnect:

    async def test_unauthenticated_closes_4001(self):
        anon = MagicMock()
        anon.is_authenticated = False
        app = ws_app(AudioStreamConsumer, user=anon)
        communicator = WebsocketCommunicator(app, '/ws/passage/1/audio/')
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4001
        await communicator.disconnect()

    async def test_etudiant_du_passage_connects(self, passage_obj, etudiant_user):
        app = ws_app(AudioStreamConsumer, user=etudiant_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        connected, _ = await communicator.connect()
        assert connected

        # Doit recevoir audio_ready
        response_text = await communicator.receive_from()
        response = json.loads(response_text)
        assert response['type'] == 'audio_ready'

        await communicator.disconnect()

    async def test_unauthorized_user_closes_4003(self, passage_obj, prof_user2):
        """Un utilisateur non affecté au passage est refusé."""
        app = ws_app(AudioStreamConsumer, user=prof_user2)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4003
        await communicator.disconnect()

    async def test_prof_du_passage_connects(self, passage_obj, prof_user):
        """Le prof responsable de la session peut aussi se connecter."""
        app = ws_app(AudioStreamConsumer, user=prof_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()  # audio_ready
        await communicator.disconnect()


# ============================================================================
# AudioStreamConsumer — réception de chunks audio
# ============================================================================

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAudioStreamConsumerReceive:

    @patch('notation.services.transcrire_audio', return_value='Voici ma présentation.')
    async def test_binary_chunk_triggers_transcription(
        self, mock_transcrire, passage_obj, etudiant_user, tmp_path, settings
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        app = ws_app(AudioStreamConsumer, user=etudiant_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()  # audio_ready

        # Envoie un chunk audio binaire
        await communicator.send_to(bytes_data=b'fake_audio_chunk_data')

        response_text = await communicator.receive_from(timeout=5)
        response = json.loads(response_text)
        assert response['type'] == 'audio_ack'
        assert response['transcrit'] is True
        assert response['texte'] == 'Voici ma présentation.'

        await communicator.disconnect()

    @patch('notation.services.transcrire_audio', return_value='')
    async def test_empty_transcription_returns_ack_false(
        self, mock_transcrire, passage_obj, etudiant_user, tmp_path, settings
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        app = ws_app(AudioStreamConsumer, user=etudiant_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        await communicator.connect()
        await communicator.receive_from()  # audio_ready

        await communicator.send_to(bytes_data=b'quiet_audio')

        response_text = await communicator.receive_from(timeout=5)
        response = json.loads(response_text)
        assert response['type'] == 'audio_ack'
        assert response['transcrit'] is False

        await communicator.disconnect()

    @patch('notation.services.transcrire_audio', return_value='Texte transcrit.')
    async def test_transcription_appended_to_passage(
        self, mock_transcrire, passage_obj, etudiant_user, tmp_path, settings
    ):
        settings.MEDIA_ROOT = str(tmp_path)
        app = ws_app(AudioStreamConsumer, user=etudiant_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        await communicator.connect()
        await communicator.receive_from()  # audio_ready

        await communicator.send_to(bytes_data=b'audio1')
        await communicator.receive_from(timeout=5)  # ack

        # Vérifie que la transcription est sauvée en BDD
        from channels.db import database_sync_to_async
        from sessions_app.models import PassageEtudiant

        @database_sync_to_async
        def get_transcription():
            return PassageEtudiant.objects.get(pk=passage_obj.pk).transcription

        transcription = await get_transcription()
        assert 'Texte transcrit.' in transcription

        await communicator.disconnect()

    @patch('notation.services.transcrire_audio', return_value='Chunk texte.')
    async def test_transcription_broadcasted_to_group(
        self, mock_transcrire, passage_obj, etudiant_user, prof_user, tmp_path, settings
    ):
        """La transcription doit être broadcastée sur le groupe du passage."""
        settings.MEDIA_ROOT = str(tmp_path)

        # Le prof se connecte au canal live
        live_app = ws_app(LivePassageConsumer, user=prof_user)
        live_comm = WebsocketCommunicator(live_app, f'/ws/passage/{passage_obj.pk}/')
        connected_live, _ = await live_comm.connect()
        assert connected_live
        await live_comm.receive_json_from()  # connected

        # L'étudiant envoie un chunk audio
        audio_app = ws_app(AudioStreamConsumer, user=etudiant_user)
        audio_comm = WebsocketCommunicator(audio_app, f'/ws/passage/{passage_obj.pk}/audio/')
        await audio_comm.connect()
        await audio_comm.receive_from()  # audio_ready

        await audio_comm.send_to(bytes_data=b'audio_data')
        await audio_comm.receive_from(timeout=5)  # ack étudiant

        # Le prof doit recevoir le broadcast transcription_chunk.
        # (un événement etudiant_connecte peut arriver avant — on l'ignore)
        response = None
        for _ in range(4):
            response = await live_comm.receive_json_from(timeout=5)
            if response['type'] == 'transcription_chunk':
                break
        assert response['type'] == 'transcription_chunk'
        assert 'Chunk texte.' in response['payload']['texte']

        await audio_comm.disconnect()
        await live_comm.disconnect()

    async def test_invalid_text_frame_ignored(self, passage_obj, etudiant_user, tmp_path, settings):
        """Une trame texte non-JSON est ignorée sans réponse ni crash."""
        settings.MEDIA_ROOT = str(tmp_path)
        app = ws_app(AudioStreamConsumer, user=etudiant_user)
        communicator = WebsocketCommunicator(app, f'/ws/passage/{passage_obj.pk}/audio/')
        await communicator.connect()
        await communicator.receive_from()  # audio_ready

        # Trame texte invalide → le consumer doit l'ignorer silencieusement
        await communicator.send_to(text_data='pas du json {{{')

        # Aucune réponse directe ne doit être envoyée
        assert await communicator.receive_nothing(timeout=0.5)

        await communicator.disconnect()
