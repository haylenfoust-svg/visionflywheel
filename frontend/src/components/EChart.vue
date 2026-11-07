<script setup lang="ts">
/**
 * EChart — thin wrapper around ECharts with a typed, role-based API.
 *
 * Charts in this app must use tokens (never raw hex). Pass a `role`
 * ('primary' | 'success' | 'warning' | 'danger' | 'info') and the wrapper
 * resolves it via `chartColor(role)`.
 *
 * Supported kinds: 'line' | 'bar' | 'pie' | 'donut' | 'area' | 'radar'.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

import { chartColor, chartFill, token } from '@/styles/tokens'

type ChartKind = 'line' | 'bar' | 'pie' | 'donut' | 'area' | 'radar'

const props = withDefaults(
  defineProps<{
    data: Array<{ label: string; value: number; color?: string }>
    kind?: ChartKind
    role?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
    height?: number
    title?: string
    showLegend?: boolean
    smooth?: boolean
  }>(),
  {
    kind: 'bar',
    role: 'primary',
    height: 220,
    title: '',
    showLegend: false,
    smooth: true,
  },
)

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const baseColor = computed(() => chartColor(props.role))
const fillColor = computed(() => chartFill(props.role))

function buildOption(): echarts.EChartsOption {
  const labels = props.data.map((d) => d.label)
  const values = props.data.map((d) => d.value)

  const grid = { left: 40, right: 20, top: props.title ? 40 : 20, bottom: 30 }

  if (props.kind === 'pie' || props.kind === 'donut') {
    return {
      title: props.title
        ? { text: props.title, left: 'center', textStyle: { fontSize: 13, color: token('neutral600') } }
        : undefined,
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: props.showLegend ? { bottom: 0 } : undefined,
      series: [
        {
          type: 'pie',
          radius: props.kind === 'donut' ? ['50%', '75%'] : '75%',
          center: ['50%', props.title ? '55%' : '50%'],
          data: props.data.map((d, i) => ({
            name: d.label,
            value: d.value,
            itemStyle: { color: d.color ?? chartColor(['primary', 'success', 'warning', 'danger', 'info'][i % 5]) },
          })),
          label: { show: false },
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowColor: 'token(neutral700)' },
            label: { show: true, fontSize: 12, fontWeight: 'bold' },
          },
        },
      ],
    }
  }

  return {
    title: props.title
      ? { text: props.title, left: 'center', textStyle: { fontSize: 13, color: token('neutral600') } }
      : undefined,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid,
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: token('neutral200') } },
      axisLabel: { color: token('neutral500'), fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: token('neutral200'), type: 'dashed' } },
      axisLabel: { color: token('neutral500'), fontSize: 10 },
    },
    series: [
      {
        type: props.kind === 'bar' ? 'bar' : 'line',
        data: values,
        smooth: props.smooth && props.kind !== 'bar',
        itemStyle: {
          color: baseColor.value,
          borderRadius: props.kind === 'bar' ? [4, 4, 0, 0] : 0,
        },
        areaStyle:
          props.kind === 'area' || props.kind === 'line'
            ? { color: fillColor.value }
            : undefined,
        lineStyle: props.kind !== 'bar' ? { width: 2, color: baseColor.value } : undefined,
        symbol: props.kind !== 'bar' ? 'circle' : undefined,
        symbolSize: props.kind !== 'bar' ? 5 : undefined,
      },
    ],
  }
}

function render() {
  if (!el.value) return
  if (!chart) {
    chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
  }
  chart.setOption(buildOption(), true)
}

function handleResize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})

watch(
  () => [props.data, props.kind, props.role, props.title],
  () => render(),
  { deep: true },
)
</script>

<template>
  <div ref="el" class="echart" :style="{ height: `${height}px`, width: '100%' }" />
</template>

<style scoped>
.echart {
  min-height: 100px;
}
</style>
