<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => (route.meta.title as string) ?? '视觉飞轮')
</script>

<template>
  <div class="app-shell">
    <header v-if="route.name !== 'login'" class="app-header">
      <div class="brand">
        <span class="brand-mark">◉</span>
        <span class="brand-name">视觉飞轮</span>
        <span class="brand-sub">VisionFlywheel</span>
      </div>
      <div class="header-title">{{ title }}</div>
    </header>
    <router-view />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: var(--vf-surface);
  border-bottom: 1px solid var(--vf-border);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.brand-mark {
  color: var(--vf-accent);
  font-size: 18px;
}
.brand-name {
  font-weight: 600;
  font-size: 16px;
}
.brand-sub {
  color: var(--vf-ink-muted);
  font-size: 12px;
}
.header-title {
  color: var(--vf-ink-muted);
  font-size: 13px;
}
</style>
