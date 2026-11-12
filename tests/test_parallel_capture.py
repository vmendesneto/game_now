"""Two sources, explicit anchors, failover and no older play overriding newer."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.asr import BYTES_PER_SECOND
from app.capture_runtime import CaptureRequest
from app.gn083_live import LiveObservation, LivePreviewRegistry
from app.main import create_app
from tests.test_capture_runtime import MATCH, SOURCE, BASE, setup, until
from tests.test_narration_tracking import game


def options(**changes):
    return {"source_id": SOURCE["id"], "permission_confirmed": True, "start_seconds":575,
            "kickoff_seconds":563, "parallel_sources":[{"source_id":"second-source", "start_seconds":2116,
            "kickoff_seconds":2104}], **changes}


@pytest.mark.parametrize("failed_source", [SOURCE["id"], "second-source"])
def test_failed_source_does_not_zero_healthy_audio_progress_or_erase_actions(tmp_path, failed_source):
    async def runner(url, match, **kwargs):
        if kwargs["source_id"] == failed_source:
            raise RuntimeError("private upstream failure")
        kwargs["on_pcm"](12*BYTES_PER_SECOND)
        await kwargs["on_observation"]({"source_id":kwargs["source_id"], "sequence":0,
            "start_seconds":0, "end_seconds":12, "text":"Azul com a bola no meio-campo pela direita"})
        await asyncio.Event().wait()
    with TestClient(create_app(tmp_path/"partial.sqlite3",capture_runner=runner)) as client:
        setup(client)
        client.put(BASE+"/sources",json=[SOURCE,{**SOURCE,"id":"second-source"}])
        assert client.post(BASE+"/capture/start",json=options()).status_code==202
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            status=client.get(BASE+"/capture").json()
            if status["observations"]==1 and any(s["state"]=="error" for s in status["streams"]):
                break
            time.sleep(.01)
        assert status["state"]=="running" and status["captured_seconds"]==12
        assert status["observations"]==1
        assert client.get(BASE+"/live/preview").json()["fusion"]["active_source_id"]!=failed_source
        assert "private upstream failure" not in str(status)


@pytest.mark.parametrize("changes", [{"kickoff_seconds":None}, {"parallel_sources":[{"source_id":SOURCE["id"],"start_seconds":2116,"kickoff_seconds":2104}]},
    {"parallel_sources":[{"source_id":"second-source","start_seconds":4269,"kickoff_seconds":2104}]},
    {"parallel_sources":[{"source_id":"second-source","start_seconds":float('inf'),"kickoff_seconds":2104}]}])
def test_invalid_or_misaligned_parallel_requests_are_rejected(changes):
    with pytest.raises(ValueError):CaptureRequest(**options(**changes))


def test_two_workers_feed_both_clients_and_stop_together_without_state_writes(tmp_path):
    closed=[]
    async def runner(url, match, **kwargs):
        try:
            kwargs['on_pcm'](6*BYTES_PER_SECOND)
            await kwargs['on_observation']({'source_id':kwargs['source_id'],'sequence':0,
                'start_seconds':0,'end_seconds':6,'text':'Azul com a bola no meio-campo pela direita'})
            await asyncio.Event().wait()
        finally:closed.append(kwargs['source_id'])
    app=create_app(tmp_path/'dual.sqlite3',capture_runner=runner)
    with TestClient(app) as client:
        setup(client)
        second={**SOURCE,'id':'second-source','name':'Second','url':'https://www.youtube.com/watch?v=second'}
        client.put(BASE+'/sources',json=[SOURCE,second])
        before=client.get(BASE+'/state').json()
        with client.websocket_connect('/ws/matches/capture-match/transcripts') as first,client.websocket_connect('/ws/matches/capture-match/transcripts') as second_ws:
            first.receive_json();second_ws.receive_json()
            started=client.post(BASE+'/capture/start',json=options())
            assert started.status_code==202,started.text
            deadline=time.monotonic()+3
            while len(client.get(BASE+'/transcripts').json()['entries'])<2:
                assert time.monotonic()<deadline;time.sleep(.01)
            for socket in (first,second_ws):
                seen=set()
                for _ in range(15):
                    message=socket.receive_json()
                    if message['kind']=='transcript':seen.add(message['data']['source_id'])
                    if len(seen)==2:break
                assert seen=={SOURCE['id'],'second-source'}
            status=client.get(BASE+'/capture').json()
            assert status['parallel'] and len(status['streams'])==2 and status['observations']==2
            assert [s['requested_start_seconds'] for s in status['streams']]==[575,2116]
            assert client.put(BASE+'/sources',json=[]).status_code==409
            assert client.post(BASE+'/capture/start',json=options()).status_code==409
            client.post(BASE+'/capture/stop');until(client,'stopped')
            assert client.get(BASE+'/live/preview').json() is None
            assert client.get(BASE+'/state').json()==before
    assert sorted(closed)==sorted([SOURCE['id'],'second-source'])


def observation(source,seq,text,end):
    return LiveObservation(source_id=source,sequence=seq,start_seconds=max(0,end-6),end_seconds=end,text=text,local_capture_age_seconds=0)


def test_commercial_on_one_source_fails_over_without_erasing_other_source():
    registry=LivePreviewRegistry()
    registry.set_alignment(game().id,{'source-one':12,'source-two':12})
    registry.receive(game(),observation('source-one',0,'Caio carrega pelo lado esquerdo do campo',6))
    assert registry.get(game().id)['source_id']=='source-one'
    registry.receive(game(),observation('source-two',0,'Beto recebeu no setor de defesa',6))
    registry.receive(game(),observation('source-one',1,'Oferecimento: uma loja',12))
    view=registry.get(game().id)
    assert view['fusion']['active_source_id']=='source-two'
    assert view['latest_narration_action']['player_id']=='beto'
    assert view['fusion']['alignment_verified'] is False
    registry.clear_source(game().id,'source-one')
    assert registry.get(game().id)['latest_narration_action']['player_id']=='beto'


def test_late_source_cannot_rewind_selected_audio_and_can_catch_up():
    registry=LivePreviewRegistry()
    registry.set_alignment(game().id,{'source-one':12,'source-two':12})
    registry.receive(game(),observation('source-one',0,'Caio recebeu no meio-campo',24))
    assert registry.get(game().id)['visual_timeline']==36
    registry.receive(game(),observation('source-one',1,'Oferecimento de uma loja',30))
    registry.receive(game(),observation('source-two',0,'Beto recebeu no setor de defesa',12))
    view=registry.get(game().id)
    assert view['fusion']['active_source_id'] is None and view['latest_narration_action'] is None
    assert view['visual_timeline']==36
    registry.receive(game(),observation('source-two',1,'Beto recebeu no meio-campo',24))
    assert registry.get(game().id)['fusion']['active_source_id']=='source-two'


def test_last_spatial_action_is_not_erased_or_assigned_to_the_next_receiver():
    registry=LivePreviewRegistry()
    view=registry.receive(game(),observation('source-one',0,'Caio recebeu no setor de defesa. Serve Davi.',12))
    assert view['latest_narration_action']['player_id']=='davi'
    assert view['latest_narration_action']['region'] is None
    assert view['latest_narration_region_action']['player_id']=='caio'
    assert view['latest_narration_region_action']['region']['bands']==[1,2]


def test_one_worker_finishing_cannot_clear_the_other_source_and_groups_are_released(tmp_path):
    async def runner(url, match, **kwargs):
        if kwargs['source_id']==SOURCE['id']:
            await asyncio.sleep(.01)
            return
        kwargs['on_pcm'](6*BYTES_PER_SECOND)
        await kwargs['on_observation']({'source_id':kwargs['source_id'],'sequence':0,
            'start_seconds':0,'end_seconds':6,'text':'Azul com a bola no meio-campo pela direita'})
        await asyncio.sleep(.15)
    app=create_app(tmp_path/'finish.sqlite3',capture_runner=runner)
    with TestClient(app) as client:
        setup(client)
        client.put(BASE+'/sources',json=[SOURCE,{**SOURCE,'id':'second-source'}])
        assert client.post(BASE+'/capture/start',json=options()).status_code==202
        deadline=time.monotonic()+2
        while client.get(BASE+'/capture').json()['streams'][0]['state']!='finished':
            assert time.monotonic()<deadline;time.sleep(.01)
        assert client.get(BASE+'/live/preview').json()['source_id']=='second-source'
        until(client,'finished')
        assert client.get(BASE+'/live/preview').json() is None
        assert app.state.capture_runtime.previews._groups=={}


def test_conflicting_full_ball_evidence_is_withheld_in_the_fused_preview():
    registry=LivePreviewRegistry()
    registry.set_alignment(game().id,{'source-one':12,'source-two':12})
    for source, text in [('source-one','Caio do Azul com a bola no meio-campo pela direita'),
                         ('source-two','Beto do Rubro com a bola no meio-campo pela esquerda')]:
        registry.receive(game(),observation(source,0,'Começou o jogo',6))
        registry.receive(game(),observation(source,1,text,12))
    view=registry.get(game().id)
    assert view['ball'] is None and view['latest_narration_region_action'] is None
    assert view['fusion']['conflicting_ball_sources']


def test_switching_to_a_source_without_whistle_does_not_reset_shared_phase_or_grant_ball_permission():
    registry=LivePreviewRegistry()
    registry.set_alignment(game().id,{'source-one':12,'source-two':12})
    registry.receive(game(),observation('source-one',0,'Começou o jogo',6))
    registry.receive(game(),observation('source-one',1,'Caio com a bola no meio-campo pela esquerda',12))
    assert registry.get(game().id)['group_phase']=='in_play'
    registry.receive(game(),observation('source-two',0,'Beto recebeu no setor de defesa',12))
    registry.receive(game(),observation('source-one',2,'Oferecimento de uma loja',18))
    view=registry.get(game().id)
    assert view['source_id']=='source-two' and view['phase']=='pre_game'
    assert view['group_phase']=='in_play' and view['group_phase_confidence']=='high'
    assert view['ball_updates_allowed'] is False


def test_shared_phase_survives_a_source_finishing_before_the_next_browser_poll():
    registry=LivePreviewRegistry()
    registry.set_alignment(game().id,{'source-one':12,'source-two':12})
    registry.receive(game(),observation('source-one',0,'Começou o jogo',6))
    registry.receive(game(),observation('source-one',1,'Caio com a bola no meio-campo pela esquerda',12))
    registry.clear_source(game().id,'source-one')
    registry.receive(game(),observation('source-two',0,'Beto recebeu no setor de defesa',12))
    assert registry.get(game().id)['group_phase']=='in_play'


def test_repeated_explicit_region_is_fresh_after_expiry_and_advertisement_cannot_keep_it_current():
    now=[0.]
    registry=LivePreviewRegistry(clock=lambda:now[0])
    registry.receive(game(),observation('source-one',0,'Começou o jogo',6))
    registry.receive(game(),observation('source-one',1,'Caio do Azul com a bola no meio-campo pela esquerda',12))
    now[0]=10
    view=registry.receive(game(),observation('source-one',2,'Davi do Azul com a bola no meio-campo pela esquerda',18))
    assert view['ball']['player_id']=='davi'
    now[0]=11
    view=registry.receive(game(),observation('source-one',3,'Oferecimento de uma loja',24))
    assert view['ball'] is None
