from io import BytesIO
from PIL import Image
import pytest
from test_api import client, HEADERS, VALID


def picture(format='PNG', size=(32, 24)):
    output = BytesIO()
    Image.new('RGB', size, 'green').save(output, format=format)
    return output.getvalue()


def test_upload_requires_token(client):
    assert client.post('/api/images', content=picture()).status_code == 401


@pytest.mark.parametrize('format', ['PNG', 'JPEG', 'WEBP'])
def test_upload_and_station_image(client, format):
    response = client.post('/api/images', content=picture(format), headers=HEADERS)
    assert response.status_code == 201
    url = response.json()['url']
    served = client.get(url)
    assert served.status_code == 200
    assert served.headers['content-type'] == 'image/jpeg'
    with Image.open(BytesIO(served.content)) as image:
        assert image.size == (32, 24)
        assert not image.getexif()
    station = client.post('/api/stations', json=VALID | {'image': url}, headers=HEADERS)
    assert station.status_code == 201
    assert station.json()['image'] == url
    assert client.get('/api/stations').json()[0]['image'] == url


def test_large_image_is_resized(client):
    response = client.post('/api/images', content=picture(size=(1800, 1200)), headers=HEADERS)
    with Image.open(BytesIO(client.get(response.json()['url']).content)) as image:
        assert image.size == (1024, 683)


@pytest.mark.parametrize('content', [b'', b'not an image', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', picture('GIF')])
def test_invalid_upload(client, content):
    assert client.post('/api/images', content=content, headers=HEADERS).status_code == 422


def test_upload_size_limit(client):
    assert client.post('/api/images', content=b'x' * (5 * 1024 * 1024 + 1), headers=HEADERS).status_code == 413


def test_resolution_limit(client, monkeypatch):
    monkeypatch.setattr('app.images.MAX_PIXELS', 100)
    assert client.post('/api/images', content=picture(), headers=HEADERS).status_code == 422


@pytest.mark.parametrize('url', ['/media/../../radio.sqlite', '/media/wrong.jpg', '/media/' + 'a' * 32 + '.svg', '//evil.test/image.jpg', 'data:image/png;base64,test'])
def test_invalid_local_paths(client, url):
    assert client.post('/api/stations', json=VALID | {'image': url}, headers=HEADERS).status_code == 422


def test_image_survives_restart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_api import TOKEN
    monkeypatch.setenv('PIRADIO_TOKEN', TOKEN)
    with TestClient(create_app(tmp_path, demo=True)) as c:
        url = c.post('/api/images', content=picture(), headers=HEADERS).json()['url']
    with TestClient(create_app(tmp_path, demo=True)) as c:
        assert c.get(url).status_code == 200
        assert c.get('/media/' + 'a' * 32 + '.jpg').status_code == 404
