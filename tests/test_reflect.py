import asyncio
import json
import httpx
import pytest
from backend_app import reflect as module
from backend_app.schemas import ReflectResponse

TEXT = '还不错夕阳照在水面上挺好看的。'


def configured(monkeypatch, replies):
    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_MODEL', 'glm-4.7-flash')
    monkeypatch.setenv('LLM_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4')
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        value = replies[min(len(requests)-1, len(replies)-1)]
        return httpx.Response(200, json={'choices':[value]})
    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    return requests


def reply(ack='水面上的夕阳，这一刻你觉得好看。', score=None):
    return {'finish_reason':'stop','message':{'content':json.dumps({'acknowledgement':ack,'change_score':score,'factors':['夕阳','编造因素'],'mismatch_stage':'none'},ensure_ascii=False)}}


def run():
    return asyncio.run(module.reflect(TEXT,place_name='屯门河道',pre_mood='累但静不下来',options=['夕阳']))


def test_transcribed_sunset_message_gets_reply_without_invented_mood_change(monkeypatch):
    requests = configured(monkeypatch, [reply()])
    result = run()
    assert result['status'] == 'ok'
    assert result['acknowledgement']
    assert result['change_score'] is None
    assert result['factors'] == ['夕阳']
    assert requests[0]['thinking'] == {'type':'disabled'}
    assert requests[0]['response_format'] == {'type':'json_object'}
    assert TEXT in requests[0]['messages'][1]['content']


@pytest.mark.parametrize('bad',[
    {'finish_reason':'length','message':{'content':'','reasoning_content':'thinking'}},
    {'finish_reason':'stop','message':{'content':None}},
    {'finish_reason':'stop','message':{'content':'[]'}},
    {'finish_reason':'stop','message':{'content':'{"acknowledgement":"'+('长'*47)+'"}'}},
])
def test_invalid_model_result_retries_instead_of_silent_empty_reply(monkeypatch,bad):
    requests = configured(monkeypatch,[bad,reply()])
    assert run()['status'] == 'ok'
    assert len(requests) == 2


def test_model_failure_is_reported_as_unavailable_not_recognition_failure(monkeypatch):
    configured(monkeypatch,[{'message':{'content':''}}])
    result = ReflectResponse(**run()).model_dump()
    assert result['status'] == 'unavailable'
    assert result['change_score'] is None
    assert result['acknowledgement'] is None


def test_followup_can_record_explicit_mood_change(monkeypatch):
    configured(monkeypatch,[reply('你现在比出发前放松了一些。',2)])
    assert run()['change_score'] == 2
