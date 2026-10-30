import asyncio
from unittest.mock import AsyncMock
import pytest
from app.models import Settings
from app.player import Player


def test_recovery_is_bounded():
    async def scenario():
        p = Player(False, Settings(auto_recover=False))
        p.resolve = AsyncMock(side_effect=RuntimeError('Offline'))
        p.station = {'id': 'test', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
        await p.run()
        assert p.state == 'error'
        assert p.resolve.await_count == 1
        await p.close()
    asyncio.run(scenario())


def test_demo_never_starts_process():
    async def scenario():
        p = Player(True, Settings())
        p.resolve = AsyncMock()
        await p.play({'id': 'demo'})
        assert p.status()['demo'] is True
        assert p.process is None
        p.resolve.assert_not_called()
        await p.close()
        assert p.state == 'stopped'
    asyncio.run(scenario())


def test_stop_cancels_resolving():
    async def scenario():
        p = Player(False, Settings())
        p.resolve = AsyncMock(side_effect=lambda _: asyncio.sleep(100))
        # Náhrada skutečného resolveru, který čeká na síť.
        async def wait(_):
            await asyncio.sleep(100)
        p.resolve = wait
        await p.play({'id': 'test', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'})
        await asyncio.sleep(0)
        await asyncio.wait_for(p.stop(), 1)
        assert p.task is None
        assert p.state == 'stopped'
        await p.close()
    asyncio.run(scenario())


def test_recovery_stops_after_four_attempts(monkeypatch):
    async def scenario():
        p = Player(False, Settings(auto_recover=True))
        p.resolve = AsyncMock(side_effect=RuntimeError('Offline'))
        p.station = {'id': 'test', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
        monkeypatch.setattr('app.player.asyncio.sleep', AsyncMock())
        await p.run()
        assert p.resolve.await_count == 4
        assert p.state == 'error'
        await p.close()
    asyncio.run(scenario())


def test_resolver_uses_project_python(monkeypatch):
    import sys
    async def scenario():
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b'https://test.googlevideo.com/audio\n', b'')
        spawn = AsyncMock(return_value=proc)
        monkeypatch.setattr('app.player.asyncio.create_subprocess_exec', spawn)
        p = Player(False, Settings())
        try:
            await p.resolve('https://www.youtube.com/watch?v=abcdefghijk')
            assert spawn.call_args.args[:3] == (sys.executable, '-m', 'yt_dlp')
        finally:
            await p.close()
    asyncio.run(scenario())


def test_cookie_file_and_plugins(monkeypatch, tmp_path):
    async def scenario():
        cookies = tmp_path / 'youtube-cookies.txt'
        cookies.write_text('# Netscape HTTP Cookie File\n')
        monkeypatch.setenv('PIRADIO_YOUTUBE_COOKIES', str(cookies))
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b'https://test.googlevideo.com/audio\n', b'')
        spawn = AsyncMock(return_value=proc)
        monkeypatch.setattr('app.player.asyncio.create_subprocess_exec', spawn)
        p = Player(False, Settings())
        await p.resolve('https://www.youtube.com/watch?v=abcdefghijk')
        args = spawn.call_args.args
        assert args[args.index('--cookies') + 1] == str(cookies)
        assert '--no-plugin-dirs' in args
        assert cookies.read_text() not in str(args)
        await p.close()
    asyncio.run(scenario())


def test_login_error_is_safe_and_not_retried(monkeypatch):
    async def scenario():
        monkeypatch.delenv('PIRADIO_YOUTUBE_COOKIES', raising=False)
        proc = AsyncMock()
        proc.returncode = 1
        proc.communicate.return_value = (b'', b'Sign in to confirm you are not a bot SECRET')
        spawn = AsyncMock(return_value=proc)
        monkeypatch.setattr('app.player.asyncio.create_subprocess_exec', spawn)
        p = Player(False, Settings(auto_recover=True))
        p.station = {'id': 'test', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
        await p.run()
        assert p.state == 'error'
        assert 'PIRADIO_YOUTUBE_COOKIES' in p.error
        assert 'SECRET' not in p.error
        assert spawn.await_count == 1
        await p.close()
    asyncio.run(scenario())


def test_missing_cookies_prevents_process(monkeypatch, tmp_path):
    from app.player import SourceError
    async def scenario():
        monkeypatch.setenv('PIRADIO_YOUTUBE_COOKIES', str(tmp_path / 'missing.txt'))
        spawn = AsyncMock()
        monkeypatch.setattr('app.player.asyncio.create_subprocess_exec', spawn)
        p = Player(False, Settings())
        with pytest.raises(SourceError):
            await p.resolve('https://www.youtube.com/watch?v=abcdefghijk')
        spawn.assert_not_called()
        await p.close()
    asyncio.run(scenario())
