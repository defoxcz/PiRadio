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
