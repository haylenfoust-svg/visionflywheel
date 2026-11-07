<script setup lang="ts">
import { computed, ref } from 'vue'

import { token } from '@/styles/tokens'

/**
 * DonutChart — proportional donut with hover segment + center total.
 */
const props = withDefaults(
  defineProps<{
    data: Array<{ label: string; value: number; color?: string }>
    title?: string
    size?: number
    thickness?: number
    centerLabel?: string
    formatValue?: (v: number) => string
  }>(),
  {
    title: '',
    size: 220,
    thickness: 22,
    centerLabel: '总计',
    formatValue: (v: number) => v.toLocaleString(),
  },
)

const hoveredIndex = ref<number | null>(null)

const total = computed(() => props.data.reduce((a, b) => a + b.value, 0) || 1)
const radius = computed(() => (props.size - props.thickness) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)

const palette = [token('chart-primary'), token('chart-success'), token('chart-warning'), token('chart-danger'), token('chart-info'), token('chart-accent'), token('chart-primary'), token('chart-success')]

function colorAt(i: number, override?: string): string {
  return override ?? palette[i % palette.length]
}

const segments = computed(() => {
  let acc = 0
  return props.data.map((d, i) => {
    const ratio = d.value / total.value
    const len = ratio * circumference.value
    const seg = {
      label: d.label,
      value: d.value,
      ratio,
      offset: -acc * circumference.value,
      length: len,
      color: colorAt(i, d.color),
    }
    acc += ratio
    return seg
  })
})

const centerValue = computed(() => {
  if (hoveredIndex.value !== null && props.data[hoveredIndex.value]) {
    return props.data[hoveredIndex.value].value
  }
  return total.value
})

const centerLabelDisplay = computed(() => {
  if (hoveredIndex.value !== null && props.data[hoveredIndex.value]) {
    return props.data[hoveredIndex.value].label
  }
  return props.centerLabel
})
</script>

<template>
  <div class="donut-chart">
    <div v-if="title" class="chart-title">{{ title }}</div>
    <div class="donut-wrap" :style="{ width: `${size}px`, height: `${size}px` }">
      <svg :viewBox="`0 0 ${size} ${size}`" class="donut-svg">
        <!-- background ring -->
        <circle
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          fill="none"
          stroke="var(--bg-subtle)"
          :stroke-width="thickness"
        />
        <!-- segments -->
        <circle
          v-for="(seg, i) in segments"
          :key="i"
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          fill="none"
          :stroke="seg.color"
          :stroke-width="hoveredIndex === i ? thickness + 3 : thickness"
          :stroke-dasharray="`${seg.length} ${circumference - seg.length}`"
          :stroke-dashoffset="seg.offset"
          stroke-linecap="butt"
          class="segment"
          @mouseenter="hoveredIndex = i"
          @mouseleave="hoveredIndex = null"
        />
        <!-- center -->
        <text :x="size / 2" :y="size / 2 - 4" text-anchor="middle" class="center-label">
          {{ centerLabelDisplay }}
        </text>
        <text :x="size / 2" :y="size / 2 + 18" text-anchor="middle" class="center-value num">
          {{ formatValue(centerValue) }}
        </text>
      </svg>
    </div>

    <!-- legend -->
    <div class="legend">
      <div
        v-for="(seg, i) in segments"
        :key="i"
        class="legend__row"
        :class="{ 'is-hover': hoveredIndex === i }"
        @mouseenter="hoveredIndex = i"
        @mouseleave="hoveredIndex = null"
      >
        <span class="legend__dot" :style="{ background: seg.color }" />
        <span class="legend__label">{{ seg.label }}</span>
        <span class="legend__value num">{{ formatValue(seg.value) }}</span>
        <span class="legend__pct num">{{ (seg.ratio * 100).toFixed(1) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.donut-chart {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.chart-title {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: var(--sp-2);
  font-weight: var(--fw-medium);
  align-self: flex-start;
}
.donut-wrap {
  position: relative;
}
.donut-svg {
  width: 100%;
  height: 100%;
}
.segment {
  transition: all var(--t-fast) var(--ease-standard);
  cursor: pointer;
  transform-origin: center;
}
.segment:hover {
  filter: brightness(1.08);
}
.center-label {
  font-size: 11px;
  fill: var(--text-tertiary);
}
.center-value {
  font-size: 22px;
  font-weight: var(--fw-semibold);
  fill: var(--text-primary);
}

.legend {
  width: 100%;
  margin-top: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.legend__row {
  display: grid;
  grid-template-columns: 12px 1fr 60px 50px;
  gap: var(--sp-2);
  align-items: center;
  padding: 4px var(--sp-2);
  border-radius: var(--r-sm);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: background var(--t-fast) var(--ease-standard);
}
.legend__row.is-hover {
  background: var(--bg-subtle);
}
.legend__dot {
  width: 8px; height: 8px;
  border-radius: var(--r-full);
}
.legend__label {
  color: var(--text-secondary);
}
.legend__value {
  text-align: right;
  font-weight: var(--fw-medium);
}
.legend__pct {
  text-align: right;
  color: var(--text-tertiary);
}
</style>
