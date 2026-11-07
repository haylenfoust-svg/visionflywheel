<script setup lang="ts">
/**
 * PageHeader — consistent page title bar with breadcrumb, description, actions.
 */
withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    breadcrumb?: Array<{ text: string; to?: string }>
  }>(),
  { subtitle: '', breadcrumb: () => [] },
)
</script>

<template>
  <header class="page-header">
    <nav v-if="breadcrumb.length" class="page-header__breadcrumb">
      <template v-for="(item, i) in breadcrumb" :key="i">
        <router-link v-if="item.to" :to="item.to" class="crumb-link">{{ item.text }}</router-link>
        <span v-else class="crumb-current">{{ item.text }}</span>
        <span v-if="i < breadcrumb.length - 1" class="crumb-sep">/</span>
      </template>
    </nav>
    <div class="page-header__row">
      <div class="page-header__titles">
        <h1 class="page-header__title">{{ title }}</h1>
        <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="page-header__actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </header>
</template>

<style scoped>
.page-header {
  margin-bottom: var(--sp-6);
  animation: slide-up var(--t-base) var(--ease-decelerate);
}
.page-header__breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
  margin-bottom: var(--sp-2);
}
.crumb-link {
  color: var(--text-secondary);
}
.crumb-link:hover { color: var(--text-accent); }
.crumb-current { color: var(--text-primary); font-weight: var(--fw-medium); }
.crumb-sep { color: var(--text-disabled); }

.page-header__row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-4);
  flex-wrap: wrap;
}
.page-header__title {
  font-size: var(--fs-2xl);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.015em;
  color: var(--text-primary);
}
.page-header__subtitle {
  margin: var(--sp-1) 0 0;
  font-size: var(--fs-md);
  color: var(--text-secondary);
  max-width: 640px;
}
.page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-shrink: 0;
}
</style>
