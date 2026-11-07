<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { healthDetail, overview } from '@/api/stats'
import type { DashboardOverview, HealthDetail } from '@/api/stats'
import { qualityMetrics } from '@/api/quality'
import type { QualityMetrics } from '@/api/quality'
import AppCard from '@/components/AppCard.vue'
import EChart from '@/components/EChart.vue'
import DonutChart from '@/components/DonutChart.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import Sparkline from '@/components/Sparkline.vue'
import StatCard from '@/components/StatCard.vue'
import SkeletonBlock from '@/components/SkeletonBlock.vue'
import { useAuthStore } from '@/stores/auth'
import { token } from '@/styles/tokens'

const router = useRouter()
const auth = useAuthStore()

const stats = ref<DashboardOverview | null>(null)
const health = ref<HealthDetail | null>(null)
const quality = ref<QualityMetrics | null>(null)
const loading = ref(true)
const range = ref<'7d' | '14d' | '30d'>('14d')

// Quality health = 100 - (fp_rate*100 + miss_rate*100) normalized
const qualityHealth = computed(() => {
  if (!quality.value) return 0
  const fp = quality.value.rates.false_positive_rate
  const miss = quality.value.rates.miss_rate_proxy
  const score = Math.max(0, 100 - (fp + miss) * 100)
  return Math.round(score)
})

// Todo quick-jumps (UI改进3)
const todos = computed(() => {
  const t = stats.value?.totals
  if (!t) return []
  const items: Array<{ label: string; count: number; icon: string; path: string; tone: string }> = []
  if ((stats.value?.by_status?.pending ?? 0) > 0) {
    items.push({
      label: '待校正检测',
      count: stats.value?.by_status?.pending ?? 0,
      icon: '✎',
      path: '/annotate',
      tone: 'warning',
    })
  }
  if (t.open_tickets > 0) {
    items.push({ label: '待处理工单', count: t.open_tickets, icon: '⚑', path: '/admin', tone: 'danger' })
  }
  if (t.datasets === 0 && (t.corrections ?? 0) > 0) {
    items.push({ label: '可导出训练集', count: 1, icon: '◈', path: '/dataset', tone: 'primary' })
  }
  return items
})


const displayName = computed(() => auth.user?.display_name || auth.user?.username || '')
const isYolo = computed(() => (health.value?.detector_mode ?? '') === 'yolo')

// ---- KPI cards with trend deltas ----
const kpis = computed(() => {
  if (!stats.value) return []
  const t = stats.value.totals
  const today = stats.value.today
  return [
    {
      key: 'detections',
      label: '识别目标',
      value: t.detections,
      delta: today.detections,
      deltaSuffix: '今日',
      accent: 'primary' as const,
      icon: '◎',
      hint: '累计检测框数量',
      path: '/detect',
    },
    {
      key: 'corrections',
      label: '校正动作',
      value: t.corrections,
      delta: today.corrections,
      deltaSuffix: '今日',
      accent: 'success' as const,
      icon: '✎',
      hint: '飞轮动力源',
      path: '/annotate',
    },
    {
      key: 'datasets',
      label: '训练集版本',
      value: t.datasets,
      delta: null,
      deltaSuffix: '',
      accent: 'neutral' as const,
      icon: '◈',
      hint: '导出的 YOLO 数据集',
      path: '/dataset',
    },
    {
      key: 'weights',
      label: '模型权重',
      value: t.weights,
      delta: null,
      deltaSuffix: '',
      accent: 'neutral' as const,
      icon: '❖',
      hint: '含训练产出',
      path: '/dataset',
    },
    {
      key: 'tickets',
      label: '待处理工单',
      value: t.open_tickets,
      delta: null,
      deltaSuffix: '',
      accent: 'warning' as const,
      icon: '⚑',
      hint: '需管理员跟进',
      path: '/admin',
    },
    {
      key: 'confidence',
      label: '平均置信度',
      value: `${(stats.value.avg_confidence * 100).toFixed(1)}%`,
      delta: null,
      deltaSuffix: '',
      accent: 'neutral' as const,
      icon: '◔',
      hint: '全量检测均值',
    },
  ]
})

// ---- Charts data ----
const classChartData = computed(() =>
  (stats.value?.by_class ?? []).map((c) => ({
    label: c.class_name_zh || c.class_name,
    value: c.count,
  })),
)

const actionChartData = computed(() =>
  Object.entries(stats.value?.by_action ?? {}).map(([label, value]) => ({ label, value })),
)

const statusDonut = computed(() => {
  const s = stats.value?.by_status ?? {}
  const labelMap: Record<string, string> = {
    pending: '待校正',
    corrected: '已校正',
    rejected: '已否决',
  }
  const colorMap: Record<string, string> = {
    pending: token('chart-warning'),
    corrected: token('chart-success'),
    rejected: token('chart-danger'),
  }
  return Object.entries(s).map(([k, v]) => ({
    label: labelMap[k] ?? k,
    value: v,
    color: colorMap[k],
  }))
})

const detectTrendData = computed(() => {
  const all = stats.value?.per_day ?? []
  return all.slice(-getRangeDays()).map((d) => ({ label: d.date.slice(5), value: d.count }))
})

const corrTrendData = computed(() => {
  const all = stats.value?.corr_per_day ?? []
  return all.slice(-getRangeDays()).map((d) => ({ label: d.date.slice(5), value: d.count }))
})

const detectSparkline = computed(() => detectTrendData.value.map((d) => d.value))

function getRangeDays(): number {
  return range.value === '7d' ? 7 : range.value === '30d' ? 30 : 14
}

// ---- Status rows for the list ----
const statusRows = computed(() => {
  const s = stats.value?.by_status ?? {}
  const total = Object.values(s).reduce((a, b) => a + b, 0) || 1
  const labelMap: Record<string, string> = {
    pending: '待校正',
    corrected: '已校正',
    rejected: '已否决',
  }
  const colorMap: Record<string, string> = {
    pending: 'var(--c-warning-500)',
    corrected: 'var(--c-success-500)',
    rejected: 'var(--c-danger-500)',
  }
  return Object.entries(s).map(([label, value]) => ({
    label: labelMap[label] ?? label,
    value,
    percent: Math.round((value / total) * 100),
    color: colorMap[label] ?? 'var(--c-neutral-400)',
  }))
})

const actionLabel: Record<string, string> = {
  confirm: '确认',
  relabel: '改标签',
  false_positive: '标误检',
  adjust: '改框',
  add: '补框',
  undo: '撤销',
}

async function refresh() {
  loading.value = true
  try {
    const [o, h, q] = await Promise.all([
      overview(),
      healthDetail(),
      qualityMetrics(30).catch(() => null),
    ])
    stats.value = o
    health.value = h
    quality.value = q
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function go(path: string) {
  router.push(path)
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader
      :title="`欢迎回来，${displayName}`"
      subtitle="识别 · 校正 · 导出 · 训练 · 切换——五步飞轮。每一次修正都让模型更强。"
    >
      <template #actions>
        <el-tag :type="isYolo ? 'success' : 'warning'" size="large" effect="light" round>
          {{ isYolo ? '⚡ YOLO 引擎' : '🛡 降级检测器' }}
        </el-tag>
        <el-button type="primary" size="large" @click="go('/detect')">
          开始识别
          <span class="btn-arrow">→</span>
        </el-button>
      </template>
    </PageHeader>

    <!-- 时间范围 -->
    <div class="range-bar">
      <div class="range-tabs">
        <button
          v-for="r in ([['7d', '近 7 天'], ['14d', '近 14 天'], ['30d', '近 30 天']] as const)"
          :key="r[0]"
          class="range-tab"
          :class="{ 'is-active': range === r[0] }"
          @click="range = r[0]"
        >
          {{ r[1] }}
        </button>
      </div>
      <div class="range-meta">
        更新于 {{ new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
      </div>
    </div>

    <!-- KPI 卡 -->
    <div v-if="loading" class="stats-grid">
      <div v-for="i in 6" :key="i" class="stat-skeleton">
        <SkeletonBlock :lines="1" height="14px" width="60%" />
        <SkeletonBlock :lines="1" height="36px" width="80%" />
        <SkeletonBlock :lines="1" height="12px" width="50%" />
      </div>
    </div>
    <div v-else-if="stats" class="stats-grid">
      <StatCard
        v-for="k in kpis"
        :key="k.key"
        :label="k.label"
        :value="k.value"
        :trend="k.delta"
        :trend-suffix="k.deltaSuffix"
        :accent="k.accent"
        :icon="k.icon"
        :hint="k.hint"
        :clickable="Boolean(k.path)"
        @click="k.path && go(k.path)"
      />
    </div>

      <!-- 待办事项 -->
      <AppCard v-if="todos.length" hoverable class="todo-card">
        <template #header>
          <SectionHeader title="待办事项" description="需要你处理" />
        </template>
        <div class="todo-list">
          <button
            v-for="todo in todos"
            :key="todo.label"
            class="todo-item"
            :class="'tone-' + todo.tone"
            @click="go(todo.path)"
          >
            <span class="todo-item__icon">{{ todo.icon }}</span>
            <div class="todo-item__body">
              <div class="todo-item__label">{{ todo.label }}</div>
              <div class="todo-item__count num">{{ todo.count }}</div>
            </div>
            <span class="todo-item__arrow">→</span>
          </button>
        </div>
      </AppCard>

    <!-- 主图表区 -->
    <template v-if="stats">
      <div class="main-grid">
        <!-- 识别趋势（大图） -->
        <AppCard hoverable class="chart-lg">
          <template #header>
            <SectionHeader
              title="识别趋势"
              :description="`近 ${getRangeDays()} 天检测数量`"
            />
          </template>
          <div class="chart-lg__body">
            <LineChart
              :data="detectTrendData"
              color="var(--c-primary-500)"
              fill-color="token('chart-fill')"
              :height="240"
            />
            <div class="chart-lg__spark">
              <span class="chart-lg__spark-label">趋势</span>
              <Sparkline :data="detectSparkline" color="var(--c-primary-500)" :width="120" :height="32" />
            </div>
          </div>
        </AppCard>

        <!-- 状态占比（环图） -->
        <AppCard hoverable class="chart-sm">
          <template #header>
            <SectionHeader title="状态占比" description="按检测状态分布" />
          </template>
          <DonutChart
            :data="statusDonut"
            :size="200"
            :thickness="22"
            center-label="检测总数"
          />
        </AppCard>
      </div>

      <div class="chart-grid">
        <AppCard hoverable>
          <template #header>
            <SectionHeader title="校正趋势" description="近两周动作次数" />
          </template>
          <LineChart
            :data="corrTrendData"
            color="var(--c-success-500)"
            fill-color="token('chart-fill-alt')"
            :height="200"
          />
        </AppCard>

        <AppCard hoverable>
          <template #header>
            <SectionHeader title="类别分布" subtitle="Top 10 · 按检测次数" />
          </template>
          <EChart :data="classChartData" kind="bar" role="primary" :height="200" />
        </AppCard>

        <AppCard hoverable>
          <template #header>
            <SectionHeader title="校正动作" subtitle="飞轮动力源 · 累计" />
          </template>
          <EChart :data="actionChartData" kind="bar" role="success" :height="200" />
        </AppCard>
      </div>

      <!-- 状态分布 + 系统状态 -->
      <div class="lower-grid">
        <AppCard>
          <template #header>
            <SectionHeader title="检测状态" description="按状态逐条" />
          </template>
          <div class="status-list">
            <div
              v-for="(row, i) in statusRows"
              :key="row.label"
              class="status-row"
              :style="{ animationDelay: `${i * 80}ms` }"
            >
              <span class="status-label">
                <span class="status-dot" :style="{ background: row.color }" />
                {{ row.label }}
              </span>
              <div class="status-track">
                <div
                  class="status-fill"
                  :style="{
                    width: `${row.percent}%`,
                    background: row.color,
                    transitionDelay: `${i * 80}ms`,
                  }"
                />
              </div>
              <span class="status-count num">{{ row.value }}</span>
            </div>
            <EmptyState
              v-if="!statusRows.length"
              title="暂无检测"
              description="上传一张图片开始识别"
              action-text="去识别"
              icon="◎"
              size="sm"
              @action="go('/detect')"
            />
          </div>
        </AppCard>

        <AppCard>
          <template #header>
            <SectionHeader title="系统状态" description="运行时元信息" />
          </template>
          <div v-if="health" class="system-grid">
            <div class="system-item">
              <div class="system-item__label">版本</div>
              <div class="system-item__value mono">{{ health.version }}</div>
            </div>
            <div class="system-item">
              <div class="system-item__label">数据库</div>
              <div class="system-item__value">
                <span class="chip" :class="health.db === 'ok' ? 'chip-success' : 'chip-danger'">
                  {{ health.db }}
                </span>
              </div>
            </div>
            <div class="system-item">
              <div class="system-item__label">检测器</div>
              <div class="system-item__value">
                <span class="chip" :class="isYolo ? 'chip-success' : 'chip-warning'">
                  {{ health.detector_mode }}
                </span>
              </div>
            </div>
            <div class="system-item">
              <div class="system-item__label">用户</div>
              <div class="system-item__value num">{{ health.user_count }}</div>
            </div>
            <div class="system-item">
              <div class="system-item__label">降级兜底</div>
              <div class="system-item__value">
                <span class="chip" :class="health.fallback_enabled ? 'chip-success' : 'chip-neutral'">
                  {{ health.fallback_enabled ? '启用' : '禁用' }}
                </span>
              </div>
            </div>
            <div class="system-item">
              <div class="system-item__label">数据库类型</div>
              <div class="system-item__value mono">{{ health.database_url_scheme }}</div>
            </div>
          </div>
        </AppCard>
      </div>

      <!-- 数据飞轮质量监控 (AI-2) -->
      <AppCard v-if="quality" hoverable class="quality-card">
        <template #header>
          <SectionHeader
            title="数据飞轮质量"
            description="误检率 / 漏检率 / 校正率 — 飞轮是否在真正改进模型"
          />
        </template>
        <div class="quality-grid">
          <div class="quality-metric">
            <div class="quality-metric__label">误检率</div>
            <div class="quality-metric__value num text-danger">
              {{ (quality.rates.false_positive_rate * 100).toFixed(1) }}%
            </div>
            <div class="quality-metric__sub">rejected / total</div>
            <Sparkline
              :data="quality.trend.detections.map((d) => d.count)"
              color="var(--c-danger-500)"
              :width="120"
              :height="28"
            />
          </div>
          <div class="quality-metric">
            <div class="quality-metric__label">人工补检率</div>
            <div class="quality-metric__value num text-warning">
              {{ (quality.rates.miss_rate_proxy * 100).toFixed(1) }}%
            </div>
            <div class="quality-metric__sub">added (manual) / total · 漏检代理</div>
            <Sparkline
              :data="quality.trend.corrections.map((d) => d.count)"
              color="var(--c-warning-500)"
              :width="120"
              :height="28"
            />
          </div>
          <div class="quality-metric">
            <div class="quality-metric__label">校正率</div>
            <div class="quality-metric__value num text-success">
              {{ (quality.rates.correction_rate * 100).toFixed(1) }}%
            </div>
            <div class="quality-metric__sub">corrected / total</div>
            <Sparkline
              :data="quality.trend.corrections.map((d) => d.count)"
              color="var(--c-success-500)"
              :width="120"
              :height="28"
            />
          </div>
          <div class="quality-metric ring">
            <div class="quality-metric__label">飞轮健康度</div>
            <div class="quality-ring">
              <svg viewBox="0 0 36 36" class="quality-ring__svg">
                <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--bg-subtle)" stroke-width="3" />
                <circle
                  cx="18"
                  cy="18"
                  r="15.5"
                  fill="none"
                  :stroke="qualityHealth >= 75 ? 'var(--c-success-500)' : qualityHealth >= 45 ? 'var(--c-warning-500)' : 'var(--c-danger-500)'"
                  stroke-width="3"
                  stroke-linecap="round"
                  :stroke-dasharray="`${(qualityHealth / 100) * 97.4} 97.4`"
                  transform="rotate(-90 18 18)"
                />
              </svg>
              <div class="quality-ring__label">
                <div class="num">{{ qualityHealth }}%</div>
                <div class="ring-sub">健康度</div>
              </div>
            </div>
            <div class="quality-metric__sub">基于误检率/补检率/校正率综合</div>
          </div>
          <div class="quality-metric">
            <div class="quality-metric__label">近 7 天检测</div>
            <div class="quality-metric__value num">
              {{ quality.window.detections.value }}
              <span
                class="quality-delta"
                :class="quality.window.detections.delta >= 0 ? 'up' : 'down'"
              >
                {{ quality.window.detections.delta >= 0 ? '+' : '' }}{{ quality.window.detections.pct }}%
              </span>
            </div>
            <div class="quality-metric__sub">vs 前 7 天</div>
          </div>
        </div>
      </AppCard>

      <!-- 最近活动 -->
      <div class="activity-grid">
        <AppCard hoverable>
          <template #header>
            <SectionHeader title="最近识别" />
          </template>
          <template #actions>
            <el-button size="small" text type="primary" @click="go('/detect')">查看全部 →</el-button>
          </template>
          <el-table v-if="stats.recent_tasks.length" :data="stats.recent_tasks" size="small" :show-header="true">
            <el-table-column prop="id" label="#" width="60" />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">
                <span class="chip chip-neutral">{{ row.type }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span
                  class="chip"
                  :class="row.status === 'done' ? 'chip-success' : row.status === 'failed' ? 'chip-danger' : 'chip-neutral'"
                >
                  {{ row.status }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="detections" label="目标" width="80" align="right" />
            <el-table-column label="引擎" width="100">
              <template #default="{ row }">
                <span class="chip" :class="row.detector_mode === 'yolo' ? 'chip-success' : 'chip-warning'">
                  {{ row.detector_mode }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            title="还没有识别记录"
            description="上传第一张图片试试"
            action-text="去上传"
            icon="◎"
            size="sm"
            @action="go('/detect')"
          />
        </AppCard>

        <AppCard hoverable>
          <template #header>
            <SectionHeader title="最近校正" />
          </template>
          <template #actions>
            <el-button size="small" text type="primary" @click="go('/annotate')">进入工作台 →</el-button>
          </template>
          <el-table v-if="stats.recent_corrections.length" :data="stats.recent_corrections" size="small">
            <el-table-column prop="id" label="#" width="60" />
            <el-table-column label="动作" width="110">
              <template #default="{ row }">
                <span class="chip" :class="row.action === 'undo' ? 'chip-warning' : 'chip-primary'">
                  {{ actionLabel[row.action] ?? row.action }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="detection_id" label="检测" width="80" align="right" />
            <el-table-column prop="operator" label="操作人" min-width="100" />
          </el-table>
          <EmptyState
            v-else
            title="还没有校正记录"
            description="校正是飞轮的动力源"
            action-text="去校正"
            icon="✎"
            size="sm"
            @action="go('/annotate')"
          />
        </AppCard>
      </div>

      <!-- 快捷入口 -->
      <AppCard title="快捷入口" class="quick-card">
        <div class="quick-grid">
          <button class="quick-item" @click="go('/detect')">
            <span class="quick-item__icon">◎</span>
            <div>
              <div class="quick-item__title">上传识别</div>
              <div class="quick-item__desc">单图 / 批量</div>
            </div>
            <span class="quick-item__arrow">→</span>
          </button>
          <button class="quick-item" @click="go('/annotate')">
            <span class="quick-item__icon">✎</span>
            <div>
              <div class="quick-item__title">校正工作台</div>
              <div class="quick-item__desc">五种校正动作</div>
            </div>
            <span class="quick-item__arrow">→</span>
          </button>
          <button class="quick-item" @click="go('/dataset')">
            <span class="quick-item__icon">◈</span>
            <div>
              <div class="quick-item__title">导出训练集</div>
              <div class="quick-item__desc">YOLO 标准格式</div>
            </div>
            <span class="quick-item__arrow">→</span>
          </button>
          <button class="quick-item" @click="go('/dataset')">
            <span class="quick-item__icon">❖</span>
            <div>
              <div class="quick-item__title">管理权重</div>
              <div class="quick-item__desc">热切换</div>
            </div>
            <span class="quick-item__arrow">→</span>
          </button>
          <button v-if="auth.isAdmin" class="quick-item" @click="go('/admin')">
            <span class="quick-item__icon">⚙</span>
            <div>
              <div class="quick-item__title">系统管理</div>
              <div class="quick-item__desc">用户 / 角色 / 权限</div>
            </div>
            <span class="quick-item__arrow">→</span>
          </button>
        </div>
      </AppCard>
    </template>
  </div>
</template>

<style scoped>
.btn-arrow {
  margin-left: var(--sp-1);
  transition: transform var(--t-fast) var(--ease-standard);
}
.el-button:hover .btn-arrow { transform: translateX(3px); }

/* 时间范围 */
.range-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-4);
}
.range-tabs {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: var(--bg-subtle);
  border-radius: var(--r-md);
}
.range-tab {
  padding: 6px var(--sp-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.range-tab:hover {
  color: var(--text-primary);
}
.range-tab.is-active {
  background: var(--bg-surface);
  color: var(--text-accent);
  font-weight: var(--fw-medium);
  box-shadow: var(--shadow-sm);
}
.range-meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

/* KPI 网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.stat-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-5);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-lg);
}

/* 主图区（一大一小） */
.main-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.chart-lg__body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.chart-lg__spark {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding-top: var(--sp-2);
  border-top: 1px solid var(--border-default);
}
.chart-lg__spark-label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

/* 三图网格 */
.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

/* 下方两栏 */
.lower-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

/* 活动流 */
.activity-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

/* 状态分布 */
.status-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.status-row {
  display: grid;
  grid-template-columns: 100px 1fr 60px;
  gap: var(--sp-3);
  align-items: center;
  animation: slide-up var(--t-base) var(--ease-decelerate) both;
}
.status-label {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.status-dot {
  width: 8px; height: 8px;
  border-radius: var(--r-full);
}
.status-track {
  height: 6px;
  background: var(--bg-subtle);
  border-radius: var(--r-full);
  overflow: hidden;
}
.status-fill {
  height: 100%;
  border-radius: var(--r-full);
  transition: width var(--t-slower) var(--ease-decelerate);
}
.status-count {
  text-align: right;
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}

/* 系统状态 */
.system-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--sp-3);
}
.system-item {
  padding: var(--sp-3);
  background: var(--bg-subtle);
  border-radius: var(--r-md);
}
.system-item__label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-bottom: 2px;
}
.system-item__value {
  font-size: var(--fs-md);
  font-weight: var(--fw-medium);
}

/* chips */
.chip {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--sp-2);
  font-size: var(--fs-xs);
  font-weight: var(--fw-medium);
  border-radius: var(--r-full);
}
.chip-primary  { color: var(--c-primary-700);  background: var(--c-primary-50); }
.chip-success  { color: var(--c-success-600);  background: var(--c-success-50); }
.chip-warning  { color: var(--c-warning-600);  background: var(--c-warning-50); }
.chip-danger   { color: var(--c-danger-600);   background: var(--c-danger-50); }
.chip-neutral  { color: var(--text-secondary);  background: var(--bg-subtle); }

/* 数据飞轮质量 */
.quality-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-3);
}
.quality-metric {
  padding: var(--sp-3);
  background: var(--bg-subtle);
  border-radius: var(--r-md);
}
.quality-metric__label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.quality-metric__value {
  font-size: var(--fs-2xl);
  font-weight: var(--fw-semibold);
  margin: 4px 0;
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}
.quality-metric__sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-bottom: var(--sp-2);
}
.quality-ring {
  position: relative;
  width: 72px;
  height: 72px;
}
.quality-ring__svg {
  width: 100%;
  height: 100%;
}
.quality-ring__label {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.quality-ring__label .num {
  font-size: var(--fs-lg);
  font-weight: var(--fw-semibold);
  line-height: 1;
}
.quality-ring__label .ring-sub {
  font-size: 9px;
  color: var(--text-tertiary);
}
.quality-metric.ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.todo-card {
  margin-bottom: var(--sp-3);
}
.todo-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-2);
}
.todo-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-subtle);
  border: 1px solid transparent;
  border-radius: var(--r-md);
  cursor: pointer;
  text-align: left;
  transition: all var(--t-fast) var(--ease-standard);
}
.todo-item:hover {
  background: var(--bg-surface);
  border-color: var(--border-accent);
  transform: translateX(2px);
}
.todo-item.tone-warning { border-left: 3px solid var(--c-warning-500); }
.todo-item.tone-danger { border-left: 3px solid var(--c-danger-500); }
.todo-item.tone-primary { border-left: 3px solid var(--c-primary-500); }
.todo-item__icon {
  width: 32px; height: 32px;
  display: grid;
  place-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-sm);
  font-size: var(--fs-md);
  flex-shrink: 0;
}
.todo-item__body {
  flex: 1;
}
.todo-item__label {
  font-size: var(--fs-base);
  font-weight: var(--fw-medium);
}
.todo-item__count {
  font-size: var(--fs-xl);
  font-weight: var(--fw-semibold);
}
.todo-item__arrow {
  color: var(--text-disabled);
  transition: transform var(--t-fast) var(--ease-standard);
}
.todo-item:hover .todo-item__arrow {
  transform: translateX(3px);
  color: var(--text-accent);
}

.quality-delta {
  font-size: var(--fs-sm);
  padding: 1px var(--sp-2);
  border-radius: var(--r-full);
}
.quality-delta.up {
  color: var(--c-success-600);
  background: var(--c-success-50);
}
.quality-delta.down {
  color: var(--c-danger-600);
  background: var(--c-danger-50);
}

/* 快捷入口 */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-2);
}
.quick-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-subtle);
  border: 1px solid transparent;
  border-radius: var(--r-md);
  cursor: pointer;
  text-align: left;
  transition: all var(--t-fast) var(--ease-standard);
}
.quick-item:hover {
  background: var(--bg-surface);
  border-color: var(--border-accent);
  transform: translateX(2px);
}
.quick-item__icon {
  width: 32px; height: 32px;
  display: grid;
  place-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-sm);
  color: var(--text-accent);
  font-size: var(--fs-md);
  flex-shrink: 0;
}
.quick-item__title {
  font-size: var(--fs-base);
  font-weight: var(--fw-medium);
}
.quick-item__desc {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.quick-item__arrow {
  margin-left: auto;
  color: var(--text-disabled);
  transition: transform var(--t-fast) var(--ease-standard);
}
.quick-item:hover .quick-item__arrow {
  transform: translateX(3px);
  color: var(--text-accent);
}

@media (max-width: 1100px) {
  .main-grid, .lower-grid, .activity-grid {
    grid-template-columns: 1fr;
  }
}
</style>
