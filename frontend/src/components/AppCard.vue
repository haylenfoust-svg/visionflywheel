<script setup lang="ts">
/**
 * AppCard — base container.
 * Subtle hover lift + focus ring. Signals layered hierarchy without shadows.
 */
withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    padded?: boolean
    hoverable?: boolean
    bordered?: boolean
  }>(),
  { padded: true, hoverable: false, bordered: true },
)
</script>

<template>
  <section
    class="app-card"
    :class="{ hoverable, 'is-padded': padded, 'is-bordered': bordered }"
  >
    <header v-if="title || $slots.header || $slots.actions" class="app-card__header">
      <div class="app-card__titles">
        <slot name="header">
          <h3 v-if="title" class="app-card__title">{{ title }}</h3>
          <p v-if="subtitle" class="app-card__subtitle">{{ subtitle }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="app-card__actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="app-card__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="app-card__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.app-card {
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  overflow: hidden;
  transition:
    border-color var(--t-fast) var(--ease-standard),
    box-shadow var(--t-fast) var(--ease-standard),
    transform var(--t-fast) var(--ease-standard);
}
.app-card.is-bordered {
  border: 1px solid var(--border-default);
}
.app-card.hoverable:hover {
  border-color: var(--border-accent);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.app-card.is-padded > .app-card__body {
  padding: var(--sp-5) var(--sp-6);
}
.app-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-6);
  border-bottom: 1px solid var(--border-default);
}
.app-card__title {
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
  color: var(--text-primary);
}
.app-card__subtitle {
  margin: 2px 0 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.app-card__footer {
  padding: var(--sp-3) var(--sp-6);
  border-top: 1px solid var(--border-default);
  background: var(--bg-subtle);
}
</style>
