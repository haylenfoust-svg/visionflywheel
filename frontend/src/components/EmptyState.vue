<script setup lang="ts">
/**
 * EmptyState — friendly empty state with illustration + primary action.
 * NN/g #8: aesthetic + minimalist; NN/g #10: help in context.
 */
withDefaults(
  defineProps<{
    title?: string
    description?: string
    actionText?: string
    icon?: string
    size?: 'sm' | 'md' | 'lg'
  }>(),
  {
    title: '暂无数据',
    description: '当前还没有可展示的内容',
    actionText: '',
    icon: '✨',
    size: 'md',
  },
)
const emit = defineEmits<{ (e: 'action'): void }>()
</script>

<template>
  <div class="empty-state" :class="`size-${size}`">
    <div class="empty-state__icon" aria-hidden="true">{{ icon }}</div>
    <h4 class="empty-state__title">{{ title }}</h4>
    <p class="empty-state__desc">{{ description }}</p>
    <slot name="action">
      <el-button v-if="actionText" type="primary" @click="emit('action')">
        {{ actionText }}
      </el-button>
    </slot>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--sp-12) var(--sp-6);
  animation: fade-in var(--t-base) var(--ease-decelerate);
}
.empty-state.size-sm { padding: var(--sp-6) var(--sp-4); }
.empty-state.size-lg { padding: var(--sp-16) var(--sp-6); }

.empty-state__icon {
  font-size: 40px;
  margin-bottom: var(--sp-3);
  padding: var(--sp-4);
  background: var(--bg-subtle);
  border-radius: var(--r-full);
  animation: scale-in var(--t-slow) var(--ease-decelerate);
}
.size-sm .empty-state__icon { font-size: 28px; padding: var(--sp-3); }

.empty-state__title {
  margin: 0 0 var(--sp-1);
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
}
.empty-state__desc {
  margin: 0 0 var(--sp-4);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  max-width: 320px;
}
</style>
