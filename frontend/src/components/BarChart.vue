<script setup lang="ts">
import { computed } from 'vue'

import { token } from '@/styles/tokens'

/** Tiny inline SVG bar chart — no external deps, keeps bundle small. */
const props = withDefaults(
  defineProps<{
    data: Array<{ label: string; value: number }>
    title?: string
    color?: string
    height?: number
    showValues?: boolean
  }>(),
  { title: '', color: token('chart-primary'), height: 160, showValues: true },
)

const padX = 32
const padY = 24
const maxValue = computed(() => Math.max(1, ...props.data.map((d) => d.value)))
const barWidth = computed(() => {
  const n = Math.max(1, props.data.length)
  return Math.min(48, Math.max(10, (320 - padX * 2) / n - 8))
})
const chartW = computed(() => Math.max(320, props.data.length * (barWidth.value + 8) + padX * 2))
const chartH = computed(() => props.height)
const innerH = computed(() => chartH.value - padY * 2)

function barHeight(value: number): number {
  return Math.max(2, (value / maxValue.value) * innerH.value)
}

function barX(index: number): number {
  return padX + index * (barWidth.value + 8)
}

function barY(value: number): number {
  return padY + innerH.value - barHeight(value)
}
</script>

<template>
  <div class="bar-chart">
    <div v-if="title" class="chart-title">{{ title }}</div>
    <svg :viewBox="`0 0 ${chartW} ${chartH}`" class="chart-svg" role="img" :aria-label="title">
      <!-- Y-axis grid lines (4) -->
      <line v-for="i in 4" :key="i" :x1="padX" :x2="chartW - padX / 2" :y1="padY + (innerH * (i - 1)) / 4" :y2="padY + (innerH * (i - 1)) / 4" class="grid" />
      <line :x1="padX" :x2="chartW - padX / 2" :y1="padY + innerH" :y2="padY + innerH" class="axis" />

      <g v-for="(d, i) in data" :key="d.label">
        <rect
          :x="barX(i)"
          :y="barY(d.value)"
          :width="barWidth"
          :height="barHeight(d.value)"
          :fill="color"
          class="bar"
        />
        <text :x="barX(i) + barWidth / 2" :y="padY + innerH + 12" text-anchor="middle" class="label">
          {{ d.label }}
        </text>
        <text
          v-if="showValues && d.value > 0"
          :x="barX(i) + barWidth / 2"
          :y="barY(d.value) - 3"
          text-anchor="middle"
          class="value"
        >
          {{ d.value }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.bar-chart {
  width: 100%;
}
.chart-title {
  font-size: 12px;
  color: var(--vf-ink-muted);
  margin-bottom: 6px;
  font-weight: 500;
}
.chart-svg {
  width: 100%;
  height: auto;
  display: block;
}
.grid {
  stroke: var(--vf-border);
  stroke-width: 0.5;
}
.axis {
  stroke: var(--vf-ink-muted);
  stroke-width: 1;
}
.bar {
  rx: 2;
}
.label {
  font-size: 9px;
  fill: var(--vf-ink-muted);
  font-family: var(--vf-font-sans);
}
.value {
  font-size: 10px;
  fill: var(--vf-ink);
  font-weight: 600;
  font-family: var(--vf-font-sans);
}
</style>
