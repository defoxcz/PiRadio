import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class Player:
    def __init__(self, demo, settings):
        self.demo = demo
        self.settings = settings
        self.process = None
        self.directory = tempfile.TemporaryDirectory(prefix='piradio-')
        self.socket = str(Path(self.directory.name) / 'mpv.sock')
        self.task = None
        self.station = None
        self.volume = settings.default_volume
        self.state = 'stopped'
        self.error = None
        self.lock = asyncio.Lock()

    def status(self):
        return dict(state=self.state, station_id=self.station['id'] if self.station else None, volume=self.volume, error=self.error, demo=self.demo)

    async def command(self, *args):
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(self.socket), 3)
        try:
            writer.write((json.dumps({'command': args}) + '\n').encode())
            await writer.drain()
            while True:
                reply = json.loads(await asyncio.wait_for(reader.readline(), 3))
                if 'error' in reply:
                    if reply['error'] != 'success':
                        raise RuntimeError(reply['error'])
                    return reply.get('data')
        finally:
            writer.close()
            await writer.wait_closed()

    async def ensure_process(self):
        if self.process and self.process.returncode is None:
            return
        self.process = await asyncio.create_subprocess_exec('mpv', '--idle=yes', '--no-video', '--no-terminal', '--network-timeout=15', '--cache-on-disk=no', '--demuxer-max-bytes=16777216', '--no-config', '--ytdl=no', '--input-terminal=no', '--input-default-bindings=no', '--load-scripts=no', f'--input-ipc-server={self.socket}', f'--audio-device={self.settings.audio_device}', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        for _ in range(50):
            try:
                await self.command('get_property', 'idle-active')
                return
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(.1)
        raise RuntimeError('mpv IPC není dostupné')

    async def resolve(self, url):
        proc = await asyncio.create_subprocess_exec(sys.executable, '-m', 'yt_dlp', '--ignore-config', '--js-runtimes', 'node', '--no-playlist', '--no-warnings', '--socket-timeout', '15', '--retries', '1', '-f', 'bestaudio/best', '--get-url', '--', url, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), 40)
        except BaseException:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            # Výstup může obsahovat podepsané URL; neukládáme jej do logu.
            detail = err.decode(errors='replace').lower()
            reason = 'neznámá chyba zdroje'
            for needle, label in [('private', 'soukromé video'), ('removed', 'odstraněné video'), ('not available in your country', 'geoblokace'), ('sign in', 'YouTube vyžaduje přihlášení'), ('javascript', 'chyba JavaScript runtime'), ('timed out', 'síťový timeout')]:
                if needle in detail:
                    reason = label
                    break
            log.warning('yt-dlp: exit=%s, příčina=%s', proc.returncode, reason)
            raise RuntimeError(f'yt-dlp skončil s kódem {proc.returncode}')
        streams = out.decode().strip().splitlines()
        if len(streams) != 1:
            raise RuntimeError('Resolver nevrátil jeden audio stream')
        u = urlparse(streams[0])
        if u.scheme != 'https' or not u.hostname or not (u.hostname.endswith('.googlevideo.com') or u.hostname == 'googlevideo.com'):
            raise RuntimeError('Nepovolená adresa audio streamu')
        return streams[0]

    async def run(self):
        attempts = 0
        while True:
            try:
                self.state = 'loading'
                stream = await self.resolve(self.station['url'])
                await self.ensure_process()
                await self.command('set_property', 'volume', self.volume)
                await self.command('loadfile', stream, 'replace')
                # Stav playing až po skutečném spuštění audio výstupu.
                for _ in range(60):
                    await asyncio.sleep(.5)
                    try:
                        audio = await self.command('get_property', 'audio-out-params')
                    except RuntimeError:
                        audio = None
                    if audio:
                        break
                else:
                    raise RuntimeError('Audio se nespustilo v časovém limitu')
                self.state = 'playing'
                self.error = None
                last_position = None
                stale_seconds = 0
                while True:
                    await asyncio.sleep(3)
                    if await self.command('get_property', 'idle-active'):
                        raise RuntimeError('Stream skončil')
                    position = await self.command('get_property', 'time-pos')
                    stale_seconds = stale_seconds + 3 if position == last_position else 0
                    last_position = position
                    if stale_seconds >= 30:
                        raise RuntimeError('Stream neposílá další audio')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('Přehrávání selhalo: %s', type(exc).__name__)
                await self.shutdown_process()
                attempts += 1
                self.error = 'Stream nelze přehrát. Může být ukončený, blokovaný nebo dočasně nedostupný.'
                if not self.settings.auto_recover or attempts >= 4:
                    self.state = 'error'
                    return
                self.state = 'loading'
                await asyncio.sleep(min(2 ** attempts, 20))

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        if not self.demo and self.process and self.process.returncode is None:
            try:
                await self.command('stop')
            except Exception:
                await self.shutdown_process()
        self.state, self.error = 'stopped', None

    async def play(self, station):
        await self.stop()
        self.station = station
        if self.demo:
            self.state = 'playing'
        else:
            self.state = 'loading'
            self.task = asyncio.create_task(self.run())

    async def set_volume(self, volume):
        if not self.demo and self.process and self.process.returncode is None:
            await self.command('set_property', 'volume', volume)
        self.volume = volume

    async def shutdown_process(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def close(self):
        await self.stop()
        await self.shutdown_process()
        self.directory.cleanup()
