<script setup lang="ts">
import { computed } from 'vue'

import { token } from '@/styles/tokens'

/**
 * Sparkline — tiny inline trend line. Fits inside a table cell or stat card.
 */
const props = withDefaults(
  defineProps<{
    data: number[]
    color?: string
    width?: number
    height?: number
    showArea?: boolean
  }>(),
  {
    color: token('chart-primary'),
    width: 100,
    height: 28,
    showArea: true,
  },
)

const max = computed(() => Math.max(1, ...props.data))
const min = computed(() => Math.min(0, ...props.data))
const range = computed(() => Math.max(1e-6, max.value - min.value))

const linePath = computed(() => {
  if (props.data.length === 0) return ''
  return props.data
    .map((v, i) => {
      const x = (i / Math.max(1, props.data.length - 1)) * props.width
      const y = props.height - ((v - min.value) / range.value) * (props.height - 4) - 2
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
})

const areaPath = computed(() => {
  if (props.data.length === 0) return ''
  const lastX = props.width
  return `${linePath.value} L ${lastX} ${props.height} L 0 ${props.height} Z`
})

const trend = computed(() => {
  if (props.data.length < 2) return 0
  return props.data[props.data.length - 1] - props.data[0]
})
</script>

<template>
  <svg
    :viewBox="`0 0 ${width} ${height}`"
    :width="width"
    :height="height"
    class="sparkline"
    :class="{ 'is-up': trend > 0, 'is-down': trend < 0 }"
  >
    <path v-if="showArea" :d="areaPath" :fill="color" opacity="0.12" />
    <path :d="linePath" fill="none" :stroke="color" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
</template>

<style scoped>
.sparkline {
  display: inline-block;
  vertical-align: middle;
  overflow: visible;
}
</style>
