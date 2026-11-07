<script setup lang="ts">
/**
 * SkeletonBlock — content placeholder that follows the shimmer heuristic
 * (NN/g #1: keeps user informed; better than a spinner for content-shaped waits).
 */
withDefaults(
  defineProps<{
    lines?: number
    height?: number | string
    width?: number | string
    variant?: 'text' | 'block' | 'circle'
  }>(),
  { lines: 1, height: '16px', width: '100%', variant: 'text' },
)
</script>

<template>
  <div class="skeleton-wrap">
    <template v-if="variant === 'text'">
      <div
        v-for="i in lines"
        :key="i"
        class="skeleton skeleton-text"
        :style="{
          width: i === lines && lines > 1 ? '65%' : width,
          height: typeof height === 'number' ? `${height}px` : height,
          animationDelay: `${i * 80}ms`,
        }"
      />
    </template>
    <div
      v-else-if="variant === 'circle'"
      class="skeleton skeleton-circle"
      :style="{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
      }"
    />
    <div
      v-else
      class="skeleton skeleton-block"
      :style="{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
      }"
    />
  </div>
</template>

<style scoped>
.skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.skeleton {
  background: linear-gradient(
    90deg,
    var(--c-neutral-200) 25%,
    var(--c-neutral-100) 50%,
    var(--c-neutral-200) 75%
  );
  background-size: 200% 100%;
  border-radius: var(--r-sm);
  animation: shimmer 1.5s var(--ease-standard) infinite;
}
.skeleton-text { border-radius: var(--r-xs); }
.skeleton-block { border-radius: var(--r-md); }
.skeleton-circle { border-radius: var(--r-full); }
</style>
