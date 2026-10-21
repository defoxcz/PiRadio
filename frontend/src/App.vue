<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api, setToken, type Station, type Status, type Settings } from "./api";
import NavIcon from "./components/NavIcon.vue";
const tabs = [
  { id: "play", label: "Přehrávání" },
  { id: "stations", label: "Stanice" },
  { id: "system", label: "Systém" },
  { id: "settings", label: "Nastavení" },
];
const tab = ref("play"),
  stations = ref<Station[]>([]),
  online = ref(false),
  error = ref(""),
  busy = ref(false),
  loading = ref(true);
const status = ref<Status>({
  state: "stopped",
  station_id: null,
  volume: 45,
  error: null,
  demo: false,
});
const feedback = ref("");
const localDemo = ref(false),
  search = ref(""),
  onlyFavorites = ref(false),
  tokenInput = ref(""),
  editing = ref(false),
  editId = ref<string | null>(null);
const form = ref({ name: "", url: "", image: "", favorite: false });
const settings = ref<Settings>({
  default_volume: 45,
  audio_device: "auto",
  auto_recover: true,
  autoplay: false,
});
interface Metrics {
  temperature: number | null;
  cpu: number;
  ram_used: number;
  ram_total: number;
  disk_used: number;
  disk_total: number;
  uptime: number;
  ips: string[];
  wifi_quality: number | null;
  throttling: number | null;
}
const metrics = ref<Metrics | null>(null),
  history = ref<{ time: number; temperature: number | null }[]>([]);
const demoStations: Station[] = [
  { id: "demo-1", name: "Noční frekvence", url: "", image: "", favorite: true },
  { id: "demo-2", name: "Klidné ráno", url: "", image: "", favorite: false },
  { id: "demo-3", name: "Jazzový pokoj", url: "", image: "", favorite: true },
];
const current = computed(
  () =>
    stations.value.find((s) => s.id === status.value.station_id) ||
    stations.value[0],
);
const visibleStations = computed(() =>
  stations.value.filter(
    (s) =>
      s.name
        .toLocaleLowerCase("cs")
        .includes(search.value.toLocaleLowerCase("cs")) &&
      (!onlyFavorites.value || s.favorite),
  ),
);
const stateLabel = computed(
  () =>
    ({
      playing: status.value.demo ? "DEMO • BEZ ZVUKU" : "ŽIVĚ",
      stopped: "ZASTAVENO",
      loading: "NAČÍTÁNÍ",
      error: "CHYBA",
    })[status.value.state] || "ZASTAVENO",
);
const graph = computed(() =>
  history.value
    .flatMap((p, i, all) =>
      p.temperature === null
        ? []
        : [
            `${(i / Math.max(all.length - 1, 1)) * 300},${90 - Math.min(100, Math.max(0, p.temperature)) * 0.8}`,
          ],
    )
    .join(" "),
);
function throttleLabel(value: number | null) {
  if (value === null) return "Nedostupné";
  if (value === 0) return "Bez příznaků";
  const flags = [
    [1, "Podpětí nyní"],
    [2, "Snížená frekvence"],
    [4, "Omezený výkon"],
    [8, "Teplotní limit"],
    [65536, "Podpětí od startu"],
    [131072, "Snížení frekvence od startu"],
    [262144, "Omezení výkonu od startu"],
    [524288, "Teplotní limit od startu"],
  ] as const;
  return (
    flags
      .filter(([bit]) => value & bit)
      .map(([, label]) => label)
      .join(" · ") || "Neznámý příznak"
  );
}
function gb(value: number) {
  return (value / 1024 ** 3).toFixed(1) + " GB";
}
async function action(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Operace se nezdařila.";
  } finally {
    busy.value = false;
  }
}
async function refresh() {
  if (localDemo.value) return;
  try {
    const [p, s] = await Promise.all([
      api<Status>("/player/status"),
      api<Station[]>("/stations"),
    ]);
    if (localDemo.value) return;
    status.value = p;
    stations.value = s;
    online.value = true;
    if (tab.value === "system") {
      try {
        const [m, h] = await Promise.all([
          api<Metrics>("/system/status"),
          api<typeof history.value>("/system/temperature-history"),
        ]);
        metrics.value = m;
        history.value = h;
      } catch (e) {
        error.value = (e as Error).message;
      }
    }
  } catch {
    online.value = false;
  } finally {
    loading.value = false;
  }
}
function preview() {
  localDemo.value = true;
  stations.value = demoStations.map((s) => ({ ...s }));
  status.value = {
    state: "stopped",
    station_id: "demo-1",
    volume: 45,
    error: null,
    demo: true,
  };
  error.value = "";
}
async function leavePreview() {
  localDemo.value = false;
  stations.value = [];
  await refresh();
}
async function play(station = current.value) {
  if (!station) {
    tab.value = "stations";
    return;
  }
  await action(async () => {
    if (localDemo.value) {
      status.value.station_id = station.id;
      status.value.state = "playing";
    } else
      status.value = await api<Status>("/player/play", "POST", {
        station_id: station.id,
      });
  });
}
async function toggle() {
  if (status.value.state === "playing" || status.value.state === "loading")
    await action(async () => {
      if (localDemo.value) status.value.state = "stopped";
      else status.value = await api<Status>("/player/stop", "POST");
    });
  else await play();
}
async function next(direction: number) {
  const i = stations.value.findIndex((s) => s.id === current.value?.id);
  const n = stations.value.length;
  if (n) await play(stations.value[(i + direction + n) % n]);
}
async function volume(event: Event) {
  const value = Number((event.target as HTMLInputElement).value);
  await action(async () => {
    if (localDemo.value) status.value.volume = value;
    else
      status.value = await api<Status>("/player/volume", "POST", {
        volume: value,
      });
  });
}
function openEditor(station?: Station) {
  editId.value = station?.id || null;
  form.value = station
    ? {
        name: station.name,
        url: station.url,
        image: station.image,
        favorite: station.favorite,
      }
    : { name: "", url: "", image: "", favorite: false };
  editing.value = true;
}
async function saveStation() {
  await action(async () => {
    if (localDemo.value) {
      const id = editId.value || crypto.randomUUID();
      stations.value = [
        ...stations.value.filter((s) => s.id !== id),
        { id, ...form.value },
      ];
    } else {
      await api(
        editId.value ? `/stations/${editId.value}` : "/stations",
        editId.value ? "PATCH" : "POST",
        form.value,
      );
      await refresh();
    }
    editing.value = false;
  });
}
async function favorite(s: Station) {
  await action(async () => {
    if (localDemo.value) s.favorite = !s.favorite;
    else {
      await api(`/stations/${s.id}`, "PATCH", { ...s, favorite: !s.favorite });
      await refresh();
    }
  });
}
async function remove(s: Station) {
  if (!confirm(`Smazat stanici „${s.name}“?`)) return;
  await action(async () => {
    if (localDemo.value)
      stations.value = stations.value.filter((x) => x.id !== s.id);
    else {
      await api(`/stations/${s.id}`, "DELETE");
      await refresh();
    }
  });
}
async function loadSettings() {
  if (localDemo.value) return;
  await action(async () => {
    settings.value = await api<Settings>("/settings");
  });
}
async function connect() {
  setToken(tokenInput.value.trim());
  tokenInput.value = "";
  await loadSettings();
  await refresh();
}
async function saveSettings() {
  await action(async () => {
    if (!localDemo.value) await api("/settings", "PATCH", settings.value);
    feedback.value = localDemo.value
      ? "Demo nastavení změněno jen v této ukázce."
      : "Nastavení bylo uloženo.";
  });
}
async function restart() {
  if (!confirm("Restartovat přehrávač? Zvuk se na chvíli přeruší.")) return;
  await action(async () => {
    if (!localDemo.value)
      status.value = await api<Status>("/player/restart", "POST");
  });
}
let timer: ReturnType<typeof setInterval>;
onMounted(() => {
  if (new URLSearchParams(location.search).get("demo") === "1") {
    preview();
    loading.value = false;
  } else void refresh();
  timer = setInterval(() => {
    if (!document.hidden && !busy.value) void refresh();
  }, 5000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <div class="shell">
    <header>
      <a class="brand" href="#" @click.prevent="tab = 'play'"
        ><NavIcon name="stations" /><span
          >pi<span class="accent">radio</span
          ><small>VÁŠ MALÝ HUDEBNÍ SVĚT</small></span
        ></a
      ><span class="connection" :class="{ connected: online && !localDemo }"
        ><i />{{
          localDemo ? "Ukázka" : online ? "Připojeno" : "Offline"
        }}</span
      >
    </header>
    <main>
      <div v-if="localDemo || status.demo" class="demo-banner">
        Demo režim · ovládání je simulované, zvuk nehraje.<button
          v-if="localDemo"
          @click="leavePreview"
        >
          Ukončit
        </button>
      </div>
      <div v-if="!online && !localDemo && !loading" class="notice">
        Server není dostupný. Zkontrolujte připojení k domácí Wi-Fi.<button
          @click="refresh"
        >
          Zkusit znovu</button
        ><button @click="preview">Prohlédnout demo</button>
      </div>
      <div v-if="error" class="notice error" role="alert">
        {{ error
        }}<button @click="error = ''" aria-label="Zavřít chybu">×</button>
      </div>
      <div v-if="feedback" class="notice" role="status">
        {{ feedback
        }}<button @click="feedback = ''" aria-label="Zavřít oznámení">×</button>
      </div>
      <p v-if="loading" role="status">Připojuji se k rádiu…</p>
      <section v-if="tab === 'play'" aria-labelledby="play-title">
        <div class="heading">
          <div>
            <p class="eyebrow">DOMA ZNÍ LÉPE</p>
            <h1 id="play-title">Teď hraje</h1>
          </div>
          <span class="sound-mark">♫</span>
        </div>
        <div class="artwork">
          <img
            v-if="current?.image"
            :src="current.image"
            alt=""
            @error="
              (e) => ((e.target as HTMLImageElement).style.display = 'none')
            "
          />
          <div class="art-orbit one" />
          <div class="art-orbit two" />
          <div class="vinyl">
            <div class="vinyl-center">π<span>RADIO</span></div>
          </div>
          <span class="art-label">SOUNDTRACK TO YOUR DAY</span
          ><span class="live" :class="status.state">● {{ stateLabel }}</span>
        </div>
        <div class="track">
          <div>
            <p class="eyebrow">
              {{ status.demo ? "UKÁZKOVÁ STANICE" : "VAŠE STANICE" }}
            </p>
            <h2>{{ current?.name || "Nalaďte si svůj svět" }}</h2>
            <p>
              {{
                current
                  ? "YouTube Live · pouze zvuk"
                  : "Přidejte první YouTube Live stanici"
              }}
            </p>
          </div>
          <button
            v-if="current"
            class="heart"
            :aria-label="
              current.favorite ? 'Odebrat z oblíbených' : 'Přidat do oblíbených'
            "
            :aria-pressed="current.favorite"
            @click="favorite(current)"
          >
            {{ current.favorite ? "♥" : "♡" }}
          </button>
        </div>
        <p v-if="status.error" class="notice error" role="alert">
          {{ status.error }}
        </p>
        <div class="transport">
          <button
            class="skip"
            aria-label="Předchozí stanice"
            :disabled="busy || !stations.length"
            @click="next(-1)"
          >
            |◀</button
          ><button
            class="play-button"
            :disabled="busy || (!online && !localDemo)"
            :aria-label="
              ['playing', 'loading'].includes(status.state)
                ? 'Zastavit'
                : 'Přehrát'
            "
            @click="toggle"
          >
            {{
              ["playing", "loading"].includes(status.state) ? "■" : "▶"
            }}</button
          ><button
            class="skip"
            aria-label="Další stanice"
            :disabled="busy || !stations.length"
            @click="next(1)"
          >
            ▶|
          </button>
        </div>
        <div class="volume">
          <label for="volume"
            >Hlasitost <strong>{{ status.volume }} %</strong></label
          ><input
            id="volume"
            type="range"
            min="0"
            max="100"
            :value="status.volume"
            :disabled="busy"
            @change="volume"
          />
          <div class="range-labels"><span>Tiše</span><span>Nahlas</span></div>
        </div>
        <div class="hint">
          <span class="accent">⌁</span>
          <p>
            Hudba zůstává doma.<br /><small
              >Telefon můžete klidně zamknout.</small
            >
          </p>
        </div>
        <button
          v-if="!stations.length && online"
          class="primary wide"
          @click="
            tab = 'stations';
            openEditor();
          "
        >
          Přidat první stanici
        </button>
      </section>
      <section v-else-if="tab === 'stations'">
        <div class="heading">
          <div>
            <p class="eyebrow">VAŠE FREKVENCE</p>
            <h1>Stanice</h1>
          </div>
          <button class="primary" @click="openEditor()">＋ Přidat</button>
        </div>
        <label class="sr-only" for="search">Vyhledat stanici</label
        ><input
          id="search"
          v-model="search"
          placeholder="Hledat v mé knihovně…"
          type="search"
        /><button
          class="filter"
          :aria-pressed="onlyFavorites"
          @click="onlyFavorites = !onlyFavorites"
        >
          {{ onlyFavorites ? "♥ Jen oblíbené" : "♡ Oblíbené" }}
        </button>
        <p class="muted">
          {{ visibleStations.length }} stanic ve vaší knihovně
        </p>
        <article
          v-for="s in visibleStations"
          :key="s.id"
          class="station-card"
          :class="{ active: status.station_id === s.id }"
        >
          <button class="station-select" @click="play(s)">
            <span class="station-art">♫</span
            ><span
              ><strong>{{ s.name }}</strong
              ><small>{{
                status.station_id === s.id
                  ? stateLabel
                  : status.demo
                    ? "Ukázka · bez zvuku"
                    : "YouTube Live"
              }}</small></span
            >
          </button>
          <div class="station-actions">
            <button
              :aria-label="
                s.favorite ? 'Odebrat oblíbenou' : 'Přidat oblíbenou'
              "
              @click="favorite(s)"
            >
              {{ s.favorite ? "♥" : "♡" }}</button
            ><button @click="openEditor(s)">Upravit</button
            ><button class="danger" @click="remove(s)">Smazat</button>
          </div>
        </article>
        <div v-if="!visibleStations.length" class="empty">
          <span>♫</span>
          <h2>
            {{ search || onlyFavorites ? "Žádná shoda" : "Vaše knihovna čeká" }}
          </h2>
          <p>Přidejte přímý HTTPS odkaz na skutečné YouTube vysílání.</p>
        </div>
        <form v-if="editing" class="panel editor" @submit.prevent="saveStation">
          <h2>{{ editId ? "Upravit stanici" : "Nová stanice" }}</h2>
          <label
            >Název<input v-model="form.name" required maxlength="100" /></label
          ><label
            >YouTube URL<input
              v-model="form.url"
              required
              type="url"
              placeholder="https://www.youtube.com/watch?v=…" /></label
          ><label
            >Obrázek (volitelně)<input
              v-model="form.image"
              type="url"
              placeholder="https://…" /></label
          ><label class="check"
            ><input v-model="form.favorite" type="checkbox" />Oblíbená
            stanice</label
          >
          <div class="row">
            <button class="primary" :disabled="busy">Uložit</button
            ><button type="button" @click="editing = false">Zrušit</button>
          </div>
        </form>
      </section>
      <section v-else-if="tab === 'system'">
        <div class="heading">
          <div>
            <p class="eyebrow">POD KAPOTOU</p>
            <h1>Systém</h1>
          </div>
          <span class="chip">↻ 5 s</span>
        </div>
        <p class="muted">
          {{
            localDemo
              ? "V ukázce nezobrazujeme smyšlené metriky."
              : "Živé údaje serveru Pi Radio"
          }}
        </p>
        <template v-if="metrics && !localDemo"
          ><div class="metric-grid">
            <article class="panel">
              <p>Teplota CPU</p>
              <strong>{{
                metrics.temperature === null
                  ? "Nedostupná"
                  : metrics.temperature.toFixed(1) + " °C"
              }}</strong>
            </article>
            <article class="panel">
              <p>Využití CPU</p>
              <strong>{{ metrics.cpu.toFixed(0) }} %</strong>
            </article>
          </div>
          <article class="panel">
            <p>RAM</p>
            <strong
              >{{ gb(metrics.ram_used) }}
              <small>/ {{ gb(metrics.ram_total) }}</small></strong
            ><meter :value="metrics.ram_used" :max="metrics.ram_total" />
            <p>Úložiště systémového disku</p>
            <strong
              >{{ gb(metrics.disk_used) }}
              <small>/ {{ gb(metrics.disk_total) }}</small></strong
            ><meter :value="metrics.disk_used" :max="metrics.disk_total" />
          </article>
          <article class="panel">
            <h2>Teplota za poslední hodinu</h2>
            <svg
              class="chart"
              viewBox="0 0 300 110"
              role="img"
              aria-label="Graf teploty CPU, vertikální rozsah 0 až 100 °C"
            >
              <path d="M0 10H300M0 50H300M0 90H300" stroke="#28363a" />
              <polyline
                :points="graph"
                fill="none"
                stroke="#75edab"
                stroke-width="2"
              />
            </svg>
            <p class="muted">
              0–100 °C · historie od startu serveru, nejvýše 1 hodina
            </p>
          </article>
          <dl class="panel details">
            <dt>Doba běhu</dt>
            <dd>
              {{ Math.floor(metrics.uptime / 3600) }} h
              {{ Math.floor((metrics.uptime % 3600) / 60) }} min
            </dd>
            <dt>IP adresa</dt>
            <dd>{{ metrics.ips.join(", ") || "Nedostupná" }}</dd>
            <dt>Wi-Fi kvalita</dt>
            <dd>
              {{
                metrics.wifi_quality === null
                  ? "Nedostupná"
                  : metrics.wifi_quality + " (Linux link quality)"
              }}
            </dd>
            <dt>Napájení / throttling</dt>
            <dd>
              {{ throttleLabel(metrics.throttling) }}
            </dd>
          </dl>
          <p class="muted">
            Příkon není měřen. Raspberry Pi nemá vestavěný wattmetr.
          </p></template
        >
        <div v-else class="panel">
          <p>
            Metriky jsou dostupné po připojení k backendu a zadání tokenu v
            Nastavení.
          </p>
        </div>
      </section>
      <section v-else>
        <div class="heading">
          <div>
            <p class="eyebrow">PODLE VÁS</p>
            <h1>Nastavení</h1>
          </div>
        </div>
        <article class="panel">
          <h2>Připojení</h2>
          <p class="server">
            {{
              localDemo
                ? "Lokální vizuální ukázka"
                : "Server: " + locationHost()
            }}
          </p>
          <form @submit.prevent="connect">
            <label
              >Ovládací token<input
                v-model="tokenInput"
                type="password"
                autocomplete="off"
                placeholder="Vložte token ze serveru"
            /></label>
            <p class="muted">Uloží se jen pro tuto relaci prohlížeče.</p>
            <button class="primary" :disabled="busy">
              Připojit a načíst nastavení
            </button>
          </form>
        </article>
        <form class="panel" @submit.prevent="saveSettings">
          <h2>Přehrávání</h2>
          <label
            >Výchozí hlasitost: {{ settings.default_volume }} %<input
              v-model.number="settings.default_volume"
              type="range"
              min="0"
              max="100" /></label
          ><label
            >Zvukový výstup mpv<input
              v-model="settings.audio_device"
              placeholder="auto"
              required
              maxlength="200"
          /></label>
          <p class="muted">
            Přesný název zjistíte přes mpv --audio-device=help. Změnu použije
            restart přehrávače.
          </p>
          <label class="check"
            ><input v-model="settings.auto_recover" type="checkbox" />Obnovit
            stream při výpadku</label
          ><label class="check"
            ><input v-model="settings.autoplay" type="checkbox" />Po startu
            přehrát poslední stanici</label
          ><button class="primary" :disabled="busy">Uložit nastavení</button>
        </form>
        <article class="panel">
          <h2>Správa zařízení</h2>
          <button class="wide" :disabled="busy" @click="restart">
            Restartovat přehrávač</button
          ><button class="wide danger" disabled>
            Vypnutí Raspberry Pi není dostupné
          </button>
          <p class="muted">Bezpečné systémové oprávnění není nastaveno.</p>
        </article>
        <button v-if="!localDemo" class="wide" @click="preview">
          Otevřít vizuální demo
        </button>
      </section>
    </main>
    <nav aria-label="Hlavní navigace">
      <button
        v-for="t in tabs"
        :key="t.id"
        :class="{ selected: tab === t.id }"
        :aria-current="tab === t.id ? 'page' : undefined"
        @click="
          tab = t.id;
          if (t.id === 'system') refresh();
          if (t.id === 'settings') loadSettings();
        "
      >
        <NavIcon :name="t.id" /><span>{{ t.label }}</span>
      </button>
    </nav>
  </div>
</template>
<script lang="ts">
function locationHost() {
  return window.location.host;
}
</script>
