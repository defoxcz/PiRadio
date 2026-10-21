import os
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import StationInput
from pydantic import ValidationError

TOKEN = 'test-token-' + 'a' * 40
HEADERS = {'Authorization': f'Bearer {TOKEN}'}
VALID = {'name': 'Testovací stanice', 'url': 'https://youtu.be/abcdefghijk'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('PIRADIO_TOKEN', TOKEN)
    with TestClient(create_app(tmp_path, demo=True)) as c:
        yield c


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://youtube.com/watch?v=abcdefghijk', 'https://youtube.com.evil.test/watch?v=abcdefghijk', 'https://localhost/foo', 'https://www.youtube.com/playlist?list=test', 'https://youtu.be/a;touch_test', 'https://user:pass@youtu.be/abcdefghijk', 'https://youtu.be:443/abcdefghijk'])
def test_invalid_sources(url):
    with pytest.raises(ValidationError):
        StationInput(name='Stanice', url=url)


def test_canonical_url():
    assert StationInput(**VALID).url == 'https://www.youtube.com/watch?v=abcdefghijk'


def test_auth_and_crud(client):
    assert client.get('/api/health').json() == {'ok': True, 'demo': True}
    assert client.get('/api/stations').json() == []
    assert client.get('/api/health').headers['cache-control'] == 'no-store'
    assert client.post('/api/stations', json=VALID).status_code == 401
    station = client.post('/api/stations', json=VALID, headers=HEADERS).json()
    id = station['id']
    assert client.patch(f'/api/stations/{id}', json=VALID | {'favorite': True}, headers=HEADERS).json()['favorite']
    assert client.post('/api/player/play', json={'station_id': id}, headers=HEADERS).json()['state'] == 'playing'
    assert client.post('/api/player/volume', json={'volume': 101}, headers=HEADERS).status_code == 422
    assert client.post('/api/player/volume', json={'volume': 0}, headers=HEADERS).json()['volume'] == 0
    assert client.delete(f'/api/stations/{id}', headers=HEADERS).status_code == 200
    assert client.get('/api/player/status').json()['state'] == 'stopped'
    assert client.post('/api/player/play', json={'station_id': id}, headers=HEADERS).status_code == 404


@pytest.mark.parametrize('path', ['/api/settings', '/api/system/status', '/api/system/temperature-history'])
def test_private_reads(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=HEADERS).status_code == 200


def test_settings_and_shutdown(client):
    settings = {'default_volume': 23, 'audio_device': 'auto', 'autoplay': False, 'auto_recover': False}
    assert client.patch('/api/settings', json=settings, headers=HEADERS).status_code == 200
    assert client.get('/api/settings', headers=HEADERS).json()['default_volume'] == 23
    assert client.post('/api/system/shutdown', headers=HEADERS).status_code == 501
    assert client.post('/api/player/restart', headers=HEADERS).status_code == 200


def test_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv('PIRADIO_TOKEN', TOKEN)
    with TestClient(create_app(tmp_path, demo=True)) as c:
        c.post('/api/stations', json=VALID, headers=HEADERS)
    with TestClient(create_app(tmp_path, demo=True)) as c:
        assert len(c.get('/api/stations').json()) == 1


def test_secret_required(tmp_path, monkeypatch):
    monkeypatch.delenv('PIRADIO_TOKEN', raising=False)
    with pytest.raises(RuntimeError):
        create_app(tmp_path, demo=True)
