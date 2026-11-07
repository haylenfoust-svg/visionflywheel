<script setup lang="ts">
/**
 * SectionHeader — small inline header with optional icon, description, action slot.
 */
withDefaults(
  defineProps<{
    title: string
    description?: string
    icon?: string
    level?: 'h2' | 'h3' | 'h4'
  }>(),
  { description: '', icon: '', level: 'h3' },
)
</script>

<template>
  <div class="section-header">
    <div class="section-header__text">
      <div class="section-header__title-row">
        <span v-if="icon" class="section-header__icon" aria-hidden="true">{{ icon }}</span>
        <component :is="level" class="section-header__title">{{ title }}</component>
      </div>
      <p v-if="description" class="section-header__desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="section-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  margin-bottom: var(--sp-3);
}
.section-header__title-row {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.section-header__icon { font-size: var(--fs-md); }
.section-header__title {
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.005em;
}
.section-header__desc {
  margin: var(--sp-1) 0 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
</style>
