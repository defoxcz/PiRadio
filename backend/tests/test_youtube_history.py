import asyncio
import sqlite3
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Settings
from app.player import Player
from app.store import Store
from app.youtube import YouTubeSearch

TOKEN = 'test-token-' + 'a' * 40
HEADERS = {'Authorization': f'Bearer {TOKEN}'}
VIDEO = 'abcdefghijk'


def test_search_uses_private_key_video_filter_cache_and_canonical_results():
    requests = []
    def response(request):
        requests.append(request)
        assert request.headers['X-Goog-Api-Key'] == 'secret-for-test'
        assert 'key=' not in str(request.url)
        assert request.url.params['type'] == 'video'
        assert request.url.params['eventType'] == 'live'
        return httpx.Response(200, json={'items': [{'id': {'videoId': VIDEO}, 'snippet': {'title': 'Jazz &amp; soul', 'channelTitle': 'Rádio', 'liveBroadcastContent': 'live'}}, {'id': {'videoId': '../bad'}}], 'nextPageToken': 'next_1'})
    async def scenario():
        service = YouTubeSearch('secret-for-test', httpx.MockTransport(response))
        data = await service.search('jazz', True)
        assert data['items'][0]['title'] == 'Jazz & soul'
        assert data['items'][0]['url'] == f'https://www.youtube.com/watch?v={VIDEO}'
        assert len(data['items']) == 1
        assert data['next_page'] == 'next_1'
        assert await service.search('jazz', True) == data
        assert len(requests) == 1
        await service.search('jazz', True, 'next_1')
        assert requests[-1].url.params['pageToken'] == 'next_1'
    asyncio.run(scenario())


@pytest.mark.parametrize('status', [403, 500])
def test_upstream_errors_do_not_leak_credentials(status):
    async def scenario():
        service = YouTubeSearch('private-key', httpx.MockTransport(lambda _: httpx.Response(status, json={'error': {'message': 'private-key'}})))
        with pytest.raises(HTTPException) as exc:
            await service.search('test')
        assert 'private-key' not in exc.value.detail
    asyncio.run(scenario())


def test_history_auto_records_persists_and_replays_without_adding_stations(tmp_path, monkeypatch):
    monkeypatch.setenv('PIRADIO_TOKEN', TOKEN)
    monkeypatch.delenv('PIRADIO_YOUTUBE_API_KEY', raising=False)
    with TestClient(create_app(tmp_path, demo=True)) as client:
        assert client.get('/api/history').status_code == 401
        assert client.get('/api/youtube/search?q=test').status_code == 401
        assert client.post('/api/youtube/play', json={'video_id': VIDEO}).status_code == 401
        assert client.get('/api/youtube/config', headers=HEADERS).json() == {'configured': False}
        assert client.get('/api/youtube/search?q=test', headers=HEADERS).status_code == 503
        assert client.post('/api/youtube/play', json={'video_id': '../bad'}, headers=HEADERS).status_code == 422
        status = client.post('/api/youtube/play', json={'video_id': VIDEO, 'title': 'Jazz', 'live': False}, headers=HEADERS).json()
        assert status['station']['name'] == 'Jazz'
        assert status['demo'] is True
        entries = client.get('/api/history', headers=HEADERS).json()
        assert len(entries) == 1 and entries[0]['demo'] is True
        assert entries[0]['name'] == 'Jazz'
        assert client.get('/api/stations').json() == []
        assert client.post(f"/api/history/{entries[0]['id']}/play", headers=HEADERS).status_code == 200
        assert len(client.get('/api/history', headers=HEADERS).json()) == 2
    with TestClient(create_app(tmp_path, demo=True)) as client:
        assert len(client.get('/api/history', headers=HEADERS).json()) == 2
        station = client.post('/api/stations', json={'name': 'Stanice', 'url': f'https://youtu.be/{VIDEO}'}, headers=HEADERS).json()
        client.post('/api/player/play', json={'station_id': station['id']}, headers=HEADERS)
        assert len(client.get('/api/history', headers=HEADERS).json()) == 3


def test_failure_is_not_playback_and_recovery_does_not_duplicate_history(monkeypatch):
    records = []
    async def scenario():
        player = Player(False, Settings(auto_recover=False), lambda station, demo: records.append(station['id']))
        player.resolve = AsyncMock(side_effect=RuntimeError('offline'))
        await player.play({'id': 'one', 'name': 'Test', 'url': f'https://youtu.be/{VIDEO}'})
        await player.task
        assert records == []
        await player.close()
    asyncio.run(scenario())


def test_successful_reconnect_records_one_history_entry(monkeypatch):
    async def scenario():
        records = []
        player = Player(False, Settings(), lambda station, demo: records.append(station['id']))
        player.station = {'id': 'live', 'url': f'https://youtu.be/{VIDEO}'}
        player.resolve = AsyncMock(return_value='https://test.googlevideo.com/audio')
        player.ensure_process = AsyncMock()
        starts = 0
        async def command(*args):
            nonlocal starts
            if args == ('get_property', 'audio-out-params'):
                starts += 1
                return {'samplerate': 48000}
            if args == ('get_property', 'idle-active'):
                if starts < 2: raise RuntimeError('connection lost')
                raise asyncio.CancelledError()
        player.command = AsyncMock(side_effect=command)
        monkeypatch.setattr('app.player.asyncio.sleep', AsyncMock())
        with pytest.raises(asyncio.CancelledError):
            await player.run()
        assert player.resolve.await_count == 2
        assert records == ['live']
        await player.close()
    asyncio.run(scenario())


def test_finite_playback_ends_without_recovery_or_duplicate_history(monkeypatch):
    async def scenario():
        records = []
        player = Player(False, Settings(), lambda station, demo: records.append(station['id']))
        player.station = {'id': 'finite', 'live': False, 'url': f'https://youtu.be/{VIDEO}'}
        player.resolve = AsyncMock(return_value='https://test.googlevideo.com/audio')
        player.ensure_process = AsyncMock()
        async def command(*args):
            if args == ('get_property', 'audio-out-params'): return {'samplerate': 48000}
            if args == ('get_property', 'eof-reached'): return True
        player.command = AsyncMock(side_effect=command)
        monkeypatch.setattr('app.player.asyncio.sleep', AsyncMock())
        await player.run()
        assert player.state == 'stopped'
        assert player.resolve.await_count == 1
        assert records == ['finite']
        await player.close()
    asyncio.run(scenario())


def test_migration_preserves_existing_station_library_and_bounds_history(tmp_path):
    path = tmp_path / 'old.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE stations (id TEXT PRIMARY KEY, name TEXT, url TEXT, image TEXT, favorite INTEGER)')
        db.execute('INSERT INTO stations VALUES (?,?,?,?,?)', ('old', 'Původní', f'https://youtu.be/{VIDEO}', '', 1))
    store = Store(path)
    try:
        station = store.station('old')
        assert station['favorite'] is True and station['live'] is True
        for _ in range(505): store.record_play(station, False)
        assert store.db.execute('SELECT COUNT(*) FROM play_history').fetchone()[0] == 500
        assert len(store.history()) == 100
        assert store.history()[0]['id'] > store.history()[-1]['id']
        assert len(store.stations()) == 1
    finally:
        store.db.close()
