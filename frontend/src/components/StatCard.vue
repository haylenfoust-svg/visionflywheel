<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

/**
 * StatCard — animated stat number + label + optional trend.
 * Count-up animation on first render and on value change (NN/g #1: visibility of status).
 */
const props = withDefaults(
  defineProps<{
    label: string
    value: number | string
    trend?: number | null        // e.g. +12 or -5 (optional delta)
    trendSuffix?: string
    accent?: 'primary' | 'success' | 'warning' | 'danger' | 'neutral'
    hint?: string
    icon?: string
    clickable?: boolean
  }>(),
  { trend: null, trendSuffix: '', accent: 'neutral', hint: '', icon: '', clickable: false },
)

const emit = defineEmits<{ (e: 'click'): void }>()

const displayed = ref(0)
const isAnimating = ref(false)

function animateTo(target: number) {
  const start = displayed.value
  const diff = target - start
  if (Math.abs(diff) < 1) {
    displayed.value = target
    return
  }
  isAnimating.value = true
  const duration = 700
  const startTime = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - startTime) / duration)
    // ease-out-expo
    const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
    displayed.value = Math.round(start + diff * eased)
    if (t < 1) requestAnimationFrame(step)
    else {
      displayed.value = target
      isAnimating.value = false
    }
  }
  requestAnimationFrame(step)
}

const numericValue = computed(() => {
  const n = typeof props.value === 'number' ? props.value : parseFloat(String(props.value))
  return Number.isFinite(n) ? n : null
})

watch(
  () => props.value,
  (v) => {
    const n = typeof v === 'number' ? v : parseFloat(String(v))
    if (Number.isFinite(n)) animateTo(n)
    else displayed.value = 0
  },
  { immediate: true },
)

onMounted(() => {
  if (numericValue.value !== null) animateTo(numericValue.value)
})

const displayValue = computed(() => {
  if (numericValue.value === null) return String(props.value)
  return displayed.value.toLocaleString()
})

const trendClass = computed(() => {
  if (props.trend == null) return ''
  return props.trend >= 0 ? 'up' : 'down'
})
</script>

<template>
  <button
    class="stat-card"
    :class="[`accent-${accent}`, { clickable, animating: isAnimating }]"
    type="button"
    :disabled="!clickable"
    @click="clickable && emit('click')"
  >
    <div class="stat-card__top">
      <span v-if="icon" class="stat-card__icon">{{ icon }}</span>
      <span class="stat-card__label">{{ label }}</span>
      <span v-if="trend != null" class="stat-card__trend" :class="trendClass">
        {{ trend > 0 ? '+' : '' }}{{ trend }}{{ trendSuffix }}
      </span>
    </div>
    <div class="stat-card__value num">{{ displayValue }}</div>
    <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
  </button>
</template>

<style scoped>
.stat-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-1);
  padding: var(--sp-5) var(--sp-5) var(--sp-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-lg);
  text-align: left;
  cursor: default;
  overflow: hidden;
  transition:
    transform var(--t-fast) var(--ease-standard),
    border-color var(--t-fast) var(--ease-standard),
    box-shadow var(--t-fast) var(--ease-standard);
  animation: slide-up var(--t-base) var(--ease-decelerate);
}
.stat-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 3px; height: 100%;
  background: transparent;
  transition: background var(--t-fast) var(--ease-standard);
}
.stat-card.clickable { cursor: pointer; }
.stat-card.clickable:hover {
  transform: translateY(-2px);
  border-color: var(--border-accent);
  box-shadow: var(--shadow-md);
}
.stat-card.clickable:hover::after { background: var(--c-primary-500); }
.stat-card:active { transform: translateY(0); }

.stat-card__top {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
}
.stat-card__icon {
  font-size: var(--fs-md);
  opacity: 0.75;
}
.stat-card__label {
  flex: 1;
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
  color: var(--text-secondary);
  letter-spacing: 0.01em;
}
.stat-card__trend {
  font-family: var(--font-num);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  padding: 1px var(--sp-2);
  border-radius: var(--r-full);
}
.stat-card__trend.up {
  color: var(--c-success-600);
  background: var(--c-success-50);
}
.stat-card__trend.down {
  color: var(--c-danger-600);
  background: var(--c-danger-50);
}

.stat-card__value {
  font-size: var(--fs-3xl);
  font-weight: var(--fw-semibold);
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  animation: count-up var(--t-slow) var(--ease-decelerate);
}
.stat-card.animating .stat-card__value {
  animation: none;
}

.stat-card__hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: 2px;
}

.stat-card.accent-primary .stat-card__value { color: var(--c-primary-600); }
.stat-card.accent-success .stat-card__value { color: var(--c-success-600); }
.stat-card.accent-warning .stat-card__value { color: var(--c-warning-600); }
.stat-card.accent-danger  .stat-card__value { color: var(--c-danger-600); }
</style>
