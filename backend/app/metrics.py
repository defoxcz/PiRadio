import asyncio
import socket
import time
from collections import deque
from pathlib import Path
import psutil


class Metrics:
    def __init__(self):
        self.history = deque(maxlen=720)

    def temperature(self):
        try:
            return float(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000
        except (OSError, ValueError):
            return None

    async def sample(self):
        while True:
            self.history.append({'time': time.time(), 'temperature': self.temperature()})
            await asyncio.sleep(5)

    async def status(self):
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        ips = [a.address for addresses in psutil.net_if_addrs().values() for a in addresses if a.family == socket.AF_INET and not a.address.startswith('127.')]
        wifi = None
        try:
            for line in Path('/proc/net/wireless').read_text().splitlines()[2:]:
                wifi = float(line.split()[2].rstrip('.'))
                break
        except (OSError, ValueError, IndexError):
            pass
        throttling = None
        try:
            proc = await asyncio.create_subprocess_exec('vcgencmd', 'get_throttled', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 2)
                throttling = int(out.decode().strip().split('=')[1], 16)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except (OSError, ValueError, IndexError):
            pass
        return dict(temperature=self.temperature(), cpu=psutil.cpu_percent(), ram_used=ram.used, ram_total=ram.total, disk_used=disk.used, disk_total=disk.total, uptime=time.time() - psutil.boot_time(), ips=ips, wifi_quality=wifi, throttling=throttling, power_watts=None, power_source='unavailable')


# Rozhraní pro budoucí externí měřič: implementace vrací skutečné W nebo None.
class PowerMeter:
    async def watts(self) -> float | None:
        return None
