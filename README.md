# Pi Radio

Domácí YouTube rádio pro Raspberry Pi 4 (2 GB), Raspberry Pi OS Lite 64-bit, USB DAC AXAGON ADA-HA a Android telefon. Vue rozhraní má centrovaný sloupec do 480 px a pevnou spodní navigaci. Telefon pouze ovládá backend; přehrávání pokračuje i po zavření stránky.

## Rychlé spuštění na Macu

Potřebujete Python 3.11+, Node.js 22.12+ a npm. Z kořene projektu:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env.local
chmod 600 .env.local
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Vygenerovaný token bezpečně vložte do `PIRADIO_TOKEN` v `.env.local`. Nezveřejňujte ho, nepřidávejte ho do Gitu. Pro první spuštění nechte `PIRADIO_DEMO=1`.

```sh
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/uvicorn app.main:create_app --factory --app-dir backend --env-file .env.local --host 127.0.0.1 --port 8000
```

Otevřete **http://127.0.0.1:8000**. Při backendu s `PIRADIO_DEMO=1` lze otevřít vizuální ukázku: **http://127.0.0.1:8000/?demo=1**. V Nastavení vložte stejný token. Nová databáze nemá žádné stanice. Tlačítko **Otevřít vizuální demo** nabídne tři jasně označené ukázky bez URL a bez zvuku. Změny v této ukázce se neukládají; ukončením se vrátíte na backend.

Backendový demo režim (`PIRADIO_DEMO=1`) ukládá skutečná data do SQLite, ale jen simuluje stav přehrávače. Každý takový stav nese `demo: true`. Nikdy neoznačuje simulaci za skutečné vysílání. Při `PIRADIO_DEMO=0` se parametr `?demo=1` ignoruje a odstraní z adresy, aby se omylem nespustila dočasná ukázka. Pro skutečný režim nastavte `PIRADIO_DEMO=0`, nainstalujte `mpv` (na Macu např. `brew install mpv`) a restartujte backend. macOS ukazuje své systémové metriky, nikoli metriky Raspberry Pi; teplota, Wi-Fi a throttling mohou být nedostupné.

Pro vývoj spusťte backend podle výše uvedeného příkazu a ve druhém terminálu `npm --prefix frontend run dev`. Vite poskytne adresu a proxy `/api` na port 8000. Frontend nemá tajemství v bundlu a nevyžaduje CORS. Backend spouštějte jen v jednom workeru: stav mpv, zámky a historie jsou záměrně v paměti jednoho procesu.

## Co je implementované

- Čtyři mobilní obrazovky: přehrávání, správa stanic, systém, nastavení. Vyhledávání, oblíbené, potvrzení smazání, nahrání obrázku ze souboru i zadání HTTPS adresy, hlasitost a předchozí/další stanice.
- SQLite v `PIRADIO_DATA`, nezávisle na zdrojovém kódu. Zapisují se jen změny stanic, nastavení a poslední stanice; nikoli každá metrika nebo změna hlasitosti.
- Dlouhodobý mpv proces s privátním Unix IPC socketem. yt-dlp získává vždy aktuální audio URL, nestahuje soubory. Povoleny jsou jen normalizované přímé YouTube HTTPS URL; resolver smí předat mpv jen HTTPS adresu na doméně `googlevideo.com`. Nepodporujeme playlisty, obecné weby ani odkazy na lokální soubory.
- Resolver má limit 40 s, IPC 3 s, síť mpv 15 s. Maximálně 4 pokusy na jeden požadavek přehrát, s prodlevou 2/4/8 s. Po vyčerpání pokusů zůstane srozumitelná chyba; nový pokus spustí uživatel. Stav přehrávání se potvrzuje dostupným audio výstupem mpv. Podepsané stream URL ani tokeny se nelogují.
- CPU, RAM, disk, uptime a IP přes psutil; dostupné linuxové teplotní a Wi-Fi údaje, throttling přes `vcgencmd`. Teplotní historie se sbírá po 5 s do paměti (nejvýše 720 bodů). UI ji načítá na systémové záložce. Disk je systémový filesystém, na Pi zpravidla microSD. Wi-Fi je syrová Linux link quality, nikoli smyšlené procento signálu.
- Příkon se nezobrazuje jako změřený. `PowerMeter.watts()` je připravený kontrakt pro externí měřič; zatím vrací `None`.
- Výchozí hlasitost se používá po startu služby / restartu přehrávače. Volitelný autostart poslední stanice platí při startu backendu.
- Restart přehrávače ukončuje a znovu zakládá mpv, nikoli systemd či OS. Vypnutí OS je vědomě nedostupné (API 501); služba nemá sudo ani práva k vypnutí.

## Raspberry Pi: nasazení přes SSH

1. Připravte Raspberry Pi OS Lite **64-bit**, Wi-Fi a SSH. Ověřte `uname -m` (aarch64), `python3 --version` (3.11+) a `node --version` (22.12+). Node musí být systémově dostupný, např. `/usr/bin/node` nebo `/usr/local/bin/node`, nikoli jen v uživatelském nvm. Instalátor Node nestahuje a při chybějícím runtime bezpečně skončí před změnami.
2. Na Macu proveďte `npm --prefix frontend ci && npm --prefix frontend run build`.
3. Přeneste projekt (doplňte svého SSH uživatele a host):

   ```sh
   rsync -av --exclude .venv --exclude node_modules --exclude '.env*' --exclude data --exclude .git ./ uzivatel@raspberrypi.local:~/PiRadio/
   ssh uzivatel@raspberrypi.local
   cd ~/PiRadio
   sudo bash deploy/install.sh
   ```

4. Instalátor vyžaduje root pouze pro instalaci balíčků, vytvoření omezeného účtu a systemd. Služba běží jako `piradio` se skupinou `audio`, kód má v `/opt/piradio`, data v `/var/lib/piradio`, tajemství v `/etc/piradio.env` (root, 0600). Existující token a data zachovává. Opakovaná instalace restartuje službu a přeruší zvuk. Neprovádí upgrade systému, vypnutí ani mazání dat. Před aktualizací zálohujte databázi při zastavené službě.
5. Ověřte `sudo systemctl status piradio` a `sudo journalctl -u piradio -n 80 --no-pager`. Token načtěte soukromě z `/etc/piradio.env`, nevkládejte ho do ticketů či logů. Systémový unit se automaticky zapne po startu Pi.

yt-dlp instalujeme s `[default]` včetně EJS komponent a explicitně používáme Node runtime. Požadavky YouTube se mohou měnit; aktuální postup je v [oficiálním EJS návodu](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Použité IPC a audio vlastnosti jsou v [manuálu mpv](https://mpv.io/manual/stable/). Instalace nemění geoblokaci, přístupová omezení ani ochrany YouTube. Ověřujte jen vysílání, k nimž máte oprávnění. Aplikace neukládá cookies a neumí přihlášené/placené přenosy. Pokud YouTube vyžaduje další ověření, přenos může být nedostupný.

## AXAGON ADA-HA / ALSA

Na Lite doporučujeme přímé ALSA, které nepotřebuje uživatelskou relaci PipeWire. Nepředpokládejte číslo zvukové karty:

```sh
aplay -l
aplay -L
mpv --audio-device=help
```

Najděte identifikátor USB karty podle skutečného výpisu. Následující `USB_ID` je **zástupný název**, nahraďte ho skutečným `CARD` identifikátorem. Začněte nízkou hlasitostí zesilovače; test ukončíte Ctrl+C:

```sh
speaker-test -D 'plughw:CARD=USB_ID,DEV=0' -c 2 -t sine
sudo -u piradio speaker-test -D 'plughw:CARD=USB_ID,DEV=0' -c 2 -t sine
```

Z výpisu `mpv --audio-device=help` zkopírujte přesný název výstupu do Nastavení, typicky `alsa/plughw:CARD=USB_ID,DEV=0`, a restartujte přehrávač. Zařízení lze také nastavit v `/etc/piradio.env` pomocí `PIRADIO_AUDIO_DEVICE`; tato hodnota při startu služby přepíše uloženou volbu. Pro trvalou volbu z UI tuto proměnnou z env souboru odstraňte. Ověřte zvuk pod účtem služby a případně mixer pomocí `alsamixer`.

Pokud už používáte PipeWire, zjistěte zařízení přes `wpctl status`, výchozí sink nastavte `wpctl set-default ID` a otestujte `speaker-test` ve stejné uživatelské relaci. Systémová služba účtu `piradio` obvykle nemá přístup k PipeWire socketu přihlášeného uživatele. Použijte ALSA, nebo samostatně připravte uživatelskou systemd službu pod účtem s PipeWire (včetně linger a správného runtime socketu). Instalátor takovou konfiguraci automaticky nemění.

## Android, LAN a PWA

Telefon připojte ke stejné domácí Wi-Fi a otevřete `http://raspberrypi.local:8000`; pokud mDNS nefunguje, použijte `http://IP_ADRESA_PI:8000`. V Nastavení vložte token. Zvuk vydává Raspberry Pi přes DAC; telefon žádné audio nepřehrává.

Službu provozujte pouze v důvěryhodné LAN. Nenastavujte port forwarding ani veřejný port. Bearer token je nutný pro všechny změny, nastavení a systémové metriky; zdravotní stav, stanice a stav přehrávače jsou čitelné bez tokenu. Každý držitel tokenu má plné ovládání, neexistují uživatelské role. Token se drží v `sessionStorage` do ukončení relace; XSS nebo nedůvěryhodný software v prohlížeči ho mohou získat. Externí obrázky se načítají přímo na telefonu, server jejich URL nestahuje. Vlastní obrázek vyberete v **Stanice → Přidat / Upravit → Obrázek ze souboru** a potvrdíte tlačítkem **Uložit**. Podporované jsou JPG, PNG a WebP do 5 MB a 16 megapixelů. Server obrázek ověří, zmenší na nejvýše 1024×1024 px a uloží jako JPEG bez původních metadat v `PIRADIO_DATA/images`. Průhlednost dostane tmavé pozadí; animace se převede na první snímek. Obrázky jsou stejně jako seznam stanic veřejně čitelné v LAN. Zálohujte celý datový adresář včetně obrázků. Odebrání obrázku ze stanice soubor automaticky nemaže, protože jej mohou používat jiné stanice; nepřiřazené soubory zatím zůstávají na disku. Ve vizuálním demu obrázek zůstane pouze v paměti prohlížeče.

HTTP v LAN nešifruje token ani provoz. Pro trvalé nasazení použijte HTTPS reverse proxy (např. Caddy) s doménou a certifikátem důvěryhodným pro Android, případně lokální CA, jejíž kořenový certifikát nainstalujete do telefonu. Pak backend přepněte na `127.0.0.1` a port zpřístupněte jen proxy. CORS není povolen; frontend a API mají stejný origin.

Manifest a SVG ikona jsou součástí aplikace. Instalovatelnost závisí na prohlížeči, jeho požadavcích na ikony a bezpečném kontextu. Běžné LAN HTTP není secure context, výjimka localhost se na IP Raspberry Pi nevztahuje. Na HTTP můžete vytvořit zástupce stránky, plnou PWA instalaci negarantujeme. Pro širší kompatibilitu lze doplnit PNG ikony 192/512 px. Service worker záměrně nepoužíváme; API se načítá s `cache: no-store`, offline se zobrazí chyba, nikoli zastaralý živý stav.

## REST API

Interaktivní schéma a všechny modely jsou v `/docs`, OpenAPI v `/openapi.json`. Chráněné operace vyžadují `Authorization: Bearer TOKEN`.

| Metoda a cesta | Tělo / význam | Token |
| --- | --- | --- |
| GET `/api/health` | `{ok, demo}` | ne |
| POST `/api/images` | binární tělo obrázku, vrací `{url}`; 201, limit 5 MB | ano |
| GET `/media/{filename}` | ověřený nahraný JPEG; chybějící obrázek 404 | ne |
| GET `/api/stations` | seznam stanic | ne |
| POST `/api/stations` | `{name, url, image?, favorite?}`; 201 | ano |
| PATCH `/api/stations/{id}` | kompletní editovatelná pole jako POST | ano |
| DELETE `/api/stations/{id}` | odstraní stanici, aktivní zastaví | ano |
| POST `/api/player/play` | `{station_id}`; asynchronní načítání | ano |
| POST `/api/player/stop` | zastavení | ano |
| POST `/api/player/volume` | `{volume: 0..100}` celé číslo | ano |
| GET `/api/player/status` | `{state, station_id, volume, error, demo}` | ne |
| GET `/api/system/status` | systémové údaje, nedostupné položky null | ano |
| GET `/api/system/temperature-history` | pole `{time: Unix sekundy, temperature: °C nebo null}` | ano |
| GET, PATCH `/api/settings` | `{default_volume, audio_device, auto_recover, autoplay}` | ano |
| POST `/api/player/restart` | bezpečný restart mpv | ano |
| POST `/api/system/shutdown` | 501, zatím nedostupné | ano |

Neplatný vstup vrací 422, chybějící token 401, neznámá stanice 404. Stav je `stopped`, `loading`, `playing` nebo `error`. Odpovědi API mají `Cache-Control: no-store`. Žádný endpoint nesestavuje shell příkaz z uživatelského vstupu. V API nejsou žádné ukázkové funkční YouTube URL.

## Ověření a omezení první verze

```sh
(cd backend && ../.venv/bin/pytest -q)
npm --prefix frontend run build
bash -n deploy/install.sh
```

Testy pokrývají odmítnutí nebezpečných URL, autentizaci, CRUD a perzistenci stanic, hlasitost, nastavení, nedostupné vypnutí, demo bez spouštění procesů, ukončení načítání a chování při chybě resolveru. Frontendová kontrola zahrnuje TypeScript a produkční build. Vizuální ověření v prohlížeči a na viewportu 360×800 nebylo v tomto prostředí dostupné; proveďte ho podle akceptačního postupu níže. `backend/requirements-lock.txt` zachycuje verze ověřené na vývojovém Macu; instalace na ARM používá přenositelné rozsahy z `requirements.txt` a správné wheel soubory pro platformu.

Na vývojovém Macu je ověřeno skutečné spuštění mpv, Unix IPC, dekódování a postup přehrávání přes CoreAudio pomocí tichého testovacího WAV při hlasitosti 0; také zastavení a ukončení procesu. Tento test nepotvrzuje konkrétní YouTube vysílání ani slyšitelný zvuk.

Skutečný YouTube stream, zvuk přes USB DAC, chování při ztrátě Wi-Fi, spotřeba paměti, automatický start po restartu Pi a oprávnění systemd je nutné ověřit na Raspberry Pi. Samotné unit testy ani stav `playing` nemohou potvrdit fyzický zvuk ze zesilovače. V prostředí vývoje není připojené Raspberry Pi ani DAC; žádné vysílání neprohlašujeme za ověřeně funkční.

Doporučený akceptační postup: nastavte skutečnou stanici → spusťte audio → zamkněte telefon na několik minut → ověřte pokračování → odpojte a obnovte Wi-Fi Pi → sledujte omezené pokusy a chybu/obnovu → restartujte Pi s autostartem → ověřte DAC a metriky → na Androidu 360×800 zkontrolujte navigaci a zvětšení textu. Vypnutí zůstává nedostupné, dokud nebude doplněn samostatný úzce oprávněný mechanismus.
