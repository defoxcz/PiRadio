<script setup lang="ts">
defineProps<{ name: string }>();
</script>
<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    aria-hidden="true"
  >
    <template v-if="name === 'play'">
      <circle cx="12" cy="12" r="9" />
      <path d="m10 8 6 4-6 4z" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'stations'">
      <rect x="4" y="7" width="16" height="14" rx="3" />
      <path d="m6 7 12-4M13 11h4m-4 4h4" />
      <circle cx="8.5" cy="14" r="2" />
    </template>
    <template v-else-if="name === 'system'">
      <path d="M3 16h4l3-9 4 13 3-8h4" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v3m0 16v3M1 12h3m16 0h3" />
    </template>
  </svg>
</template>
