<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * LineChart — animated area/line chart with hover tooltip and axis labels.
 * Self-contained SVG (no deps) so the bundle stays small and consistent.
 */
const props = withDefaults(
  defineProps<{
    data: Array<{ label: string; value: number }>
    title?: string
    color?: string
    fillColor?: string
    height?: number
    showDots?: boolean
    showArea?: boolean
    formatValue?: (v: number) => string
  }>(),
  {
    title: '',
    color: '#6366f1',
    fillColor: 'rgba(99, 102, 241, 0.14)',
    height: 220,
    showDots: true,
    showArea: true,
    formatValue: (v: number) => v.toLocaleString(),
  },
)

const svgRef = ref<SVGSVGElement | null>(null)
const hoveredIndex = ref<number | null>(null)
const cursor = ref<{ x: number; y: number } | null>(null)

const padX = 36
const padY = 20
const chartW = 640

const maxValue = computed(() => Math.max(1, ...props.data.map((d) => d.value)))
const innerW = computed(() => chartW - padX * 2)
const innerH = computed(() => props.height - padY * 2 - 18)

function x(i: number): number {
  const n = Math.max(1, props.data.length - 1)
  return padX + (i / n) * innerW.value
}

function y(v: number): number {
  return padY + innerH.value - (v / maxValue.value) * innerH.value
}

function nearestIndex(relX: number): number {
  let best = 0
  let bestDist = Infinity
  for (let i = 0; i < props.data.length; i += 1) {
    const d = Math.abs(x(i) - relX)
    if (d < bestDist) {
      bestDist = d
      best = i
    }
  }
  return best
}

const linePath = computed(() => {
  if (props.data.length === 0) return ''
  return props.data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(d.value)}`).join(' ')
})

const areaPath = computed(() => {
  if (props.data.length === 0) return ''
  const base = `L ${x(props.data.length - 1)} ${padY + innerH.value} L ${padX} ${padY + innerH.value} Z`
  return `${linePath.value} ${base}`
})

const gridLines = computed(() => {
  const lines = []
  for (let i = 0; i <= 4; i += 1) {
    const v = (maxValue.value * (4 - i)) / 4
    lines.push({ y: padY + (innerH.value * i) / 4, value: v })
  }
  return lines
})

const labelStep = computed(() => Math.max(1, Math.ceil(props.data.length / 8)))

function onMove(ev: MouseEvent) {
  const svg = svgRef.value
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  const relX = ((ev.clientX - rect.left) / rect.width) * chartW
  const best = nearestIndex(relX)
  hoveredIndex.value = best
  const px = (x(best) / chartW) * rect.width
  const py = (y(props.data[best].value) / props.height) * rect.height
  cursor.value = { x: px, y: py }
}

function onLeave() {
  hoveredIndex.value = null
  cursor.value = null
}
</script>

<template>
  <div class="line-chart">
    <div v-if="title" class="chart-title">{{ title }}</div>
    <div class="chart-wrap" :style="{ height: `${height}px` }">
      <svg
        ref="svgRef"
        :viewBox="`0 0 ${chartW} ${height}`"
        class="chart-svg"
        preserveAspectRatio="none"
        role="img"
        :aria-label="title"
        @mousemove="onMove"
        @mouseleave="onLeave"
      >
        <!-- grid -->
        <line
          v-for="(g, i) in gridLines"
          :key="i"
          :x1="padX"
          :x2="chartW - padX / 2"
          :y1="g.y"
          :y2="g.y"
          class="grid"
        />

        <!-- area -->
        <path v-if="showArea" :d="areaPath" :fill="fillColor" class="area" />

        <!-- line -->
        <path :d="linePath" fill="none" :stroke="color" stroke-width="2.2" class="line" />

        <!-- dots -->
        <g v-if="showDots">
          <circle
            v-for="(d, i) in data"
            :key="i"
            :cx="x(i)"
            :cy="y(d.value)"
            :r="hoveredIndex === i ? 5 : 3"
            :fill="hoveredIndex === i ? color : '#fff'"
            :stroke="color"
            stroke-width="1.8"
            class="dot"
          />
        </g>

        <!-- hover crosshair -->
        <g v-if="hoveredIndex !== null">
          <line
            :x1="x(hoveredIndex)"
            :x2="x(hoveredIndex)"
            :y1="padY"
            :y2="padY + innerH"
            class="crosshair"
          />
        </g>

        <!-- x labels -->
        <g>
          <text
            v-for="(d, i) in data"
            v-show="i % labelStep === 0 || i === data.length - 1"
            :key="`l-${i}`"
            :x="x(i)"
            :y="height - 4"
            text-anchor="middle"
            class="axis-label"
          >
            {{ d.label }}
          </text>
        </g>
      </svg>

      <!-- tooltip -->
      <div
        v-if="hoveredIndex !== null && cursor"
        class="tooltip"
        :style="{
          left: `${(x(hoveredIndex) / chartW) * 100}%`,
          top: `${(y(data[hoveredIndex].value) / height) * 100}%`,
        }"
      >
        <div class="tooltip__label">{{ data[hoveredIndex].label }}</div>
        <div class="tooltip__value num" :style="{ color }">
          {{ formatValue(data[hoveredIndex].value) }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-chart {
  width: 100%;
}
.chart-title {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: var(--sp-2);
  font-weight: var(--fw-medium);
}
.chart-wrap {
  position: relative;
  width: 100%;
}
.chart-svg {
  width: 100%;
  height: 100%;
  display: block;
  overflow: visible;
}
.grid {
  stroke: var(--border-default);
  stroke-width: 0.5;
  stroke-dasharray: 3 3;
}
.area {
  transition: opacity var(--t-fast) var(--ease-standard);
}
.line {
  stroke-linecap: round;
  stroke-linejoin: round;
}
.dot {
  transition: all var(--t-fast) var(--ease-standard);
}
.crosshair {
  stroke: var(--c-neutral-300);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}
.axis-label {
  font-size: 9px;
  fill: var(--text-tertiary);
  font-family: var(--font-sans);
}

.tooltip {
  position: absolute;
  transform: translate(-50%, -110%);
  padding: 6px 10px;
  background: var(--c-neutral-900);
  color: white;
  border-radius: var(--r-sm);
  pointer-events: none;
  white-space: nowrap;
  font-size: var(--fs-xs);
  box-shadow: var(--shadow-lg);
  z-index: 10;
}
.tooltip__label {
  opacity: 0.75;
  margin-bottom: 2px;
}
.tooltip__value {
  font-weight: var(--fw-semibold);
  font-size: var(--fs-md);
}
</style>
