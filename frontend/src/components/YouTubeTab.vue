<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { api, type Status } from "../api";
interface Video {
  video_id: string;
  title: string;
  channel: string;
  live: boolean;
  url: string;
  image: string;
}
interface Entry {
  id: number;
  name: string;
  image: string;
  started_at: string;
  demo: boolean;
}
const props = defineProps<{ disabled: boolean; demo: boolean }>();
const emit = defineEmits<{ playing: [Status]; saved: [] }>();
const query = ref(""),
  live = ref(false),
  configured = ref(false),
  searching = ref(false),
  acting = ref(false);
const results = ref<Video[]>([]),
  nextPage = ref<string | null>(null),
  searched = ref(false);
const error = ref(""),
  notice = ref(""),
  historyError = ref(""),
  entries = ref<Entry[]>([]);
let request = 0;
watch([query, live], () => {
  request++;
  results.value = [];
  nextPage.value = null;
  searched.value = false;
  error.value = "";
});
onBeforeUnmount(() => request++);
async function loadHistory() {
  if (props.demo) return;
  historyError.value = "";
  try {
    entries.value = await api<Entry[]>("/history");
  } catch (e) {
    historyError.value = (e as Error).message;
  }
}
onMounted(async () => {
  if (props.demo) return;
  await Promise.all([
    api<{ configured: boolean }>("/youtube/config")
      .then((value) => {
        configured.value = value.configured;
      })
      .catch((e) => {
        error.value = e.message;
      }),
    loadHistory(),
  ]);
});
async function search(more = false) {
  if (!query.value.trim() || searching.value) return;
  const sequence = ++request;
  const params = new URLSearchParams({
    q: query.value.trim(),
    live: String(live.value),
  });
  if (more && nextPage.value) params.set("page", nextPage.value);
  searching.value = true;
  error.value = "";
  notice.value = "";
  if (!more) {
    results.value = [];
    nextPage.value = null;
  }
  try {
    const data = await api<{ items: Video[]; next_page: string | null }>(
      `/youtube/search?${params}`,
    );
    if (sequence !== request) return;
    const combined = more ? [...results.value, ...data.items] : data.items;
    results.value = combined.filter(
      (item, index) =>
        combined.findIndex((other) => other.video_id === item.video_id) ===
        index,
    );
    nextPage.value = data.next_page;
    searched.value = true;
  } catch (e) {
    if (sequence === request) error.value = (e as Error).message;
  } finally {
    searching.value = false;
  }
}
async function play(video: Video) {
  acting.value = true;
  error.value = "";
  try {
    emit(
      "playing",
      await api<Status>("/youtube/play", "POST", {
        video_id: video.video_id,
        title: video.title,
        live: video.live,
      }),
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    acting.value = false;
  }
}
async function save(video: Video) {
  acting.value = true;
  error.value = "";
  notice.value = "";
  try {
    await api("/stations", "POST", {
      name: video.title,
      url: video.url,
      image: video.image,
      favorite: false,
      live: video.live,
    });
    notice.value = "Uloženo mezi stanice.";
    emit("saved");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    acting.value = false;
  }
}
async function replay(entry: Entry) {
  acting.value = true;
  historyError.value = "";
  try {
    emit("playing", await api<Status>(`/history/${entry.id}/play`, "POST"));
  } catch (e) {
    historyError.value = (e as Error).message;
  } finally {
    acting.value = false;
  }
}
</script>

<template>
  <section aria-labelledby="youtube-title">
    <div class="heading">
      <div>
        <p class="eyebrow">HLEDEJTE A POSLOUCHEJTE</p>
        <h1 id="youtube-title">YouTube</h1>
      </div>
    </div>
    <p class="muted">
      Vyberte video nebo živé vysílání. Zvuk přehraje rádio přes svůj audio
      výstup.
    </p>
    <p v-if="demo" class="notice">
      Ve vizuálním demu není dostupné skutečné hledání ani historie.
    </p>
    <p v-else-if="!configured && !error" class="notice">
      Vyhledávání není na rádiu nastavené. Doplňte na serveru
      PIRADIO_YOUTUBE_API_KEY pro YouTube Data API v3 a restartujte službu.
      Historie funguje i bez klíče.
    </p>
    <form class="youtube-search" @submit.prevent="search()">
      <label for="youtube-query">Najít na YouTube</label>
      <input
        id="youtube-query"
        v-model="query"
        type="search"
        maxlength="200"
        placeholder="Interpret, skladba, rádio…"
        :disabled="searching || demo"
        required
      />
      <label class="youtube-check"
        ><input v-model="live" type="checkbox" :disabled="searching || demo" />
        Pouze živé vysílání</label
      >
      <button
        class="wide"
        :disabled="!configured || disabled || searching || !query.trim()"
      >
        {{ searching ? "Hledám…" : "Hledat" }}
      </button>
    </form>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="searched && !results.length" role="status">
      Žádné odpovídající video.
    </p>
    <article
      v-for="video in results"
      :key="video.video_id"
      class="youtube-result"
    >
      <img
        :src="video.image"
        alt=""
        loading="lazy"
        referrerpolicy="no-referrer"
      />
      <div>
        <a :href="video.url" target="_blank" rel="noopener noreferrer">{{
          video.title
        }}</a>
        <p class="muted">
          {{ video.channel }}<span v-if="video.live"> · Živě</span>
        </p>
        <div class="youtube-actions">
          <button :disabled="disabled || acting" @click="play(video)">
            ▶ Přehrát na rádiu</button
          ><button :disabled="disabled || acting" @click="save(video)">
            Uložit stanici
          </button>
        </div>
      </div>
    </article>
    <button
      v-if="nextPage"
      class="wide"
      :disabled="searching || disabled"
      @click="search(true)"
    >
      Další výsledky
    </button>
    <div class="heading">
      <h2>Historie přehrávání</h2>
      <button :disabled="demo || acting" @click="loadHistory">Obnovit</button>
    </div>
    <p class="muted">
      Spuštěné streamy se ukládají automaticky na rádiu. Posledních 100
      spuštění, nejnovější nahoře.
    </p>
    <p v-if="historyError" class="notice error" role="alert">
      {{ historyError }}
    </p>
    <p v-else-if="!entries.length" class="muted">Historie je zatím prázdná.</p>
    <article
      v-for="entry in entries"
      :key="entry.id"
      class="youtube-result history-result"
    >
      <div>
        <h3>{{ entry.name }}</h3>
        <p class="muted">
          {{ new Date(entry.started_at).toLocaleString("cs-CZ")
          }}<span v-if="entry.demo"> · Demo bez zvuku</span>
        </p>
        <button :disabled="disabled || acting" @click="replay(entry)">
          ▶ Znovu přehrát na rádiu
        </button>
      </div>
    </article>
  </section>
</template>
