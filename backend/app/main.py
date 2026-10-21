import asyncio
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from .models import StationInput, Volume, Play, Settings
from .store import Store
from .player import Player
from .metrics import Metrics


def create_app(data_dir=None, demo=None):
    data = Path(data_dir or os.getenv('PIRADIO_DATA', './data'))
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = os.getenv('PIRADIO_TOKEN', '')
    demo = os.getenv('PIRADIO_DEMO', '0') == '1' if demo is None else demo
    if len(token) < 32:
        raise RuntimeError('Nastavte PIRADIO_TOKEN na náhodný token o nejméně 32 znacích.')
    store = Store(data / 'radio.sqlite')
    settings = Settings(**store.get('settings', {}))
    settings.audio_device = os.getenv('PIRADIO_AUDIO_DEVICE', settings.audio_device)
    player = Player(demo, settings)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(app):
        sampler = asyncio.create_task(metrics.sample())
        if settings.autoplay:
            station = store.station(store.get('last_station'))
            if station:
                await player.play(station)
        yield
        sampler.cancel()
        await asyncio.gather(sampler, return_exceptions=True)
        await player.close()
        store.db.close()

    app = FastAPI(title='Pi Radio', lifespan=lifespan)

    @app.middleware('http')
    async def no_api_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    async def auth(authorization: str = Header(default='')):
        if not hmac.compare_digest(authorization.encode(), f'Bearer {token}'.encode()):
            raise HTTPException(401, 'Neplatný ovládací token.')

    write = [Depends(auth)]

    @app.get('/api/health')
    async def health():
        return {'ok': True, 'demo': demo}

    @app.get('/api/stations')
    async def stations():
        return store.stations()

    @app.post('/api/stations', dependencies=write, status_code=201)
    async def add(value: StationInput):
        return store.save(value)

    @app.patch('/api/stations/{id}', dependencies=write)
    async def edit(id: str, value: StationInput):
        if not store.station(id):
            raise HTTPException(404, 'Stanice neexistuje.')
        return store.save(value, id)

    @app.delete('/api/stations/{id}', dependencies=write)
    async def delete(id: str):
        if not store.station(id):
            raise HTTPException(404, 'Stanice neexistuje.')
        async with player.lock:
            if player.station and player.station['id'] == id:
                await player.stop()
            store.delete(id)
        return {'ok': True}

    @app.post('/api/player/play', dependencies=write)
    async def play(value: Play):
        station = store.station(value.station_id)
        if not station:
            raise HTTPException(404, 'Stanice neexistuje.')
        async with player.lock:
            await player.play(station)
            store.set('last_station', station['id'])
        return player.status()

    @app.post('/api/player/stop', dependencies=write)
    async def stop():
        async with player.lock:
            await player.stop()
        return player.status()

    @app.post('/api/player/volume', dependencies=write)
    async def volume(value: Volume):
        async with player.lock:
            try:
                await player.set_volume(value.volume)
            except Exception:
                raise HTTPException(503, 'Přehrávač nereaguje. Zkuste jej restartovat.')
        return player.status()

    @app.get('/api/player/status')
    async def status():
        return player.status()

    @app.get('/api/system/status', dependencies=write)
    async def system():
        return await metrics.status()

    @app.get('/api/system/temperature-history', dependencies=write)
    async def history():
        return list(metrics.history)

    @app.get('/api/settings', dependencies=write)
    async def get_settings():
        return settings.model_dump() | {'shutdown_available': False}

    @app.patch('/api/settings', dependencies=write)
    async def save_settings(value: Settings):
        # Zařízení je argument mpv, nikdy shell příkaz. Nový výstup platí po restartu mpv.
        for key, val in value.model_dump().items():
            setattr(settings, key, val)
        store.set('settings', settings.model_dump())
        return settings.model_dump()

    @app.post('/api/player/restart', dependencies=write)
    async def restart():
        async with player.lock:
            station = player.station if player.state != 'stopped' else None
            await player.stop()
            await player.shutdown_process()
            player.volume = settings.default_volume
            if station:
                await player.play(station)
        return player.status()

    @app.post('/api/system/shutdown', dependencies=write)
    async def shutdown():
        raise HTTPException(501, 'Bezpečné vypnutí není na tomto serveru nakonfigurováno.')

    dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app
