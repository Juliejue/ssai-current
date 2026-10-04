import base64
import json

import httpx
from fastapi.testclient import TestClient

from backend_app.main import app
from backend_app import companion, speech

client = TestClient(app)


def test_actions_are_shared_and_private_text_is_discarded(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    code = client.post('/api/v1/relay/sessions').json()['code']
    for action in ('accept', 'change', 'quiet', 'near'):
        response = client.post(f'/api/v1/relay/{code}/events', json={'event_type':'companion_action', 'payload':{'action':action,'origin':'desk','request_id':action,'text':'private utterance'}})
        assert response.status_code == 202
    events = client.get(f'/api/v1/relay/{code}').json()['events']
    assert [e['payload']['action'] for e in events] == ['accept','change','quiet','near']
    assert all('text' not in e['payload'] for e in events)
    invalid = client.post(f'/api/v1/relay/{code}/events', json={'event_type':'companion_action','payload':{'action':'delete_all','origin':'desk','request_id':'bad'}})
    assert invalid.status_code == 400


def test_blank_chat_rejected_and_unconfigured_chat_honest(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('api_key', raising=False)
    assert client.post('/api/v1/companion/chat', json={'text':'  '}).status_code == 422
    result = client.post('/api/v1/companion/chat', json={'text':'还想继续聊聊'}).json()
    assert result['source'] == 'rules'
    assert result['urgent'] is False


def test_urgent_chat_does_not_call_model(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','test-key')
    result = client.post('/api/v1/companion/chat', json={'text':'我想自杀'}).json()
    assert result['urgent'] is True
    assert result['source'] == 'safety'


def test_tts_unconfigured_keeps_text_and_no_system_fallback(monkeypatch):
    monkeypatch.delenv('TENCENT_SECRET_ID', raising=False)
    monkeypatch.delenv('TENCENT_SECRET_KEY', raising=False)
    assert client.get('/api/v1/speech/capabilities').json()['configured'] is False
    assert client.post('/api/v1/speech', json={'text':'我在。'}).status_code == 503
    assert client.post('/api/v1/speech', json={'text':'x'*151}).status_code == 422


def test_fixed_voice_and_credentials_never_in_audio_response(monkeypatch):
    monkeypatch.setenv('TENCENT_SECRET_ID','test-id')
    monkeypatch.setenv('TENCENT_SECRET_KEY','test-secret')
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'Response':{'Audio':base64.b64encode(b'ID3test-mp3').decode()}})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(speech.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    response = client.post('/api/v1/speech', json={'text':'我在，慢慢说。'})
    assert response.status_code == 200
    assert response.content == b'ID3test-mp3'
    assert response.headers['cache-control'] == 'no-store'
    body = json.loads(requests[0].content)
    assert body['VoiceType'] == 502001
    assert body['Speed'] < 0
    assert 'test-secret' not in requests[0].headers['authorization']
    assert b'test-secret' not in response.content


def test_tts_permission_error_is_actionable(monkeypatch):
    monkeypatch.setenv('TENCENT_SECRET_ID','test-id')
    monkeypatch.setenv('TENCENT_SECRET_KEY','test-secret')
    real_client = httpx.AsyncClient
    monkeypatch.setattr(speech.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda _: httpx.Response(200,json={'Response':{'Error':{'Code':'InvalidParameterValue.AppIdNotRegistered'}}})), **kwargs))
    response = client.post('/api/v1/speech',json={'text':'我在。'})
    assert response.status_code == 503
    assert '开通' in response.json()['detail']


def test_failed_durable_action_never_claims_success(monkeypatch):
    from backend_app import relay
    monkeypatch.delenv('DATABASE_URL', raising=False)
    code = client.post('/api/v1/relay/sessions').json()['code']
    monkeypatch.setenv('DATABASE_URL', 'postgresql://not-connected')
    async def fail(*args, **kwargs):
        raise relay.psycopg.OperationalError('database unavailable')
    monkeypatch.setattr(relay.psycopg.AsyncConnection, 'connect', fail)
    response = client.post(f'/api/v1/relay/{code}/events', json={'event_type':'companion_action','payload':{'action':'change','origin':'desk','request_id':'failure'}})
    assert response.status_code == 503
    monkeypatch.delenv('DATABASE_URL')
    assert client.get(f'/api/v1/relay/{code}').json()['events'] == []


def test_extension_transport_keeps_old_schema_and_checks_commands():
    from backend_app.relay import _storage_event, _display_event, safe_payload
    clean = safe_payload('companion_action', {'action':'quiet','origin':'desk','request_id':'demo','text':'private'})
    stored_type, envelope = _storage_event('companion_action', clean)
    assert stored_type == 'collector_saved'
    assert _display_event(stored_type,envelope) == ('companion_action',clean)
    assert 'text' not in envelope['data']
    forged = {'_current_extension_v1':'companion_action','data':{'action':'delete_all','origin':'desk','request_id':'bad'}}
    assert _display_event('collector_saved',forged) == ('collector_saved',{})


def test_extension_write_works_with_original_database_whitelist(monkeypatch):
    from backend_app import relay
    original_types = {'interpreted','recommended','departed','arrived','feedback','collector_saved'}
    stored = []
    class Cursor:
        async def fetchone(self):
            return (101,)
    class Connection:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def execute(self, sql, params):
            if params[0] not in original_types:
                raise relay.psycopg.errors.CheckViolation('original whitelist')
            stored.append((params[0],json.loads(params[1])))
            return Cursor()
    async def connect(*args, **kwargs): return Connection()
    monkeypatch.setenv('DATABASE_URL','postgresql://original-schema')
    monkeypatch.setattr(relay.psycopg.AsyncConnection,'connect',connect)
    response = client.post('/api/v1/relay/ABCD23/events',json={'event_type':'companion_action','payload':{'action':'change','origin':'desk','request_id':'compat'}})
    assert response.status_code == 202
    assert response.json()['durable'] is True
    assert relay._display_event(*stored[0])[0] == 'companion_action'
