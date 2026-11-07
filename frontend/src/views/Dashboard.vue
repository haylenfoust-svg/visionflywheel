<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { healthDetail, overview } from '@/api/stats'
import type { DashboardOverview, HealthDetail } from '@/api/stats'
import BarChart from '@/components/BarChart.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const stats = ref<DashboardOverview | null>(null)
const health = ref<HealthDetail | null>(null)
const loading = ref(false)

const displayName = computed(() => auth.user?.display_name || auth.user?.username || '')
const detectorTag = computed(() => {
  const mode = health.value?.detector_mode
  if (mode === 'yolo') return { text: 'YOLO', type: 'success' as const }
  return { text: '降级检测器', type: 'warning' as const }
})

const classChartData = computed(() =>
  (stats.value?.by_class ?? []).map((c) => ({
    label: c.class_name_zh || c.class_name,
    value: c.count,
  })),
)

const actionChartData = computed(() =>
  Object.entries(stats.value?.by_action ?? {}).map(([label, value]) => ({ label, value })),
)

const detectTrendData = computed(() =>
  (stats.value?.per_day ?? []).map((d) => ({
    label: d.date.slice(5),
    value: d.count,
  })),
)

const corrTrendData = computed(() =>
  (stats.value?.corr_per_day ?? []).map((d) => ({
    label: d.date.slice(5),
    value: d.count,
  })),
)

const statusRows = computed(() => {
  const s = stats.value?.by_status ?? {}
  const total = Object.values(s).reduce((a, b) => a + b, 0) || 1
  return Object.entries(s).map(([label, value]) => ({
    label,
    value,
    percent: Math.round((value / total) * 100),
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

const statusLabel: Record<string, string> = {
  pending: '待校正',
  corrected: '已校正',
  rejected: '已否决',
  done: '已完成',
  running: '处理中',
  failed: '失败',
  open: '待处理',
  replied: '已回复',
  resolved: '已解决',
}

async function refresh() {
  loading.value = true
  try {
    const [o, h] = await Promise.all([overview(), healthDetail()])
    stats.value = o
    health.value = h
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
  <div class="page dashboard">
    <header class="hero">
      <div>
        <h2>欢迎回来，{{ displayName }}</h2>
        <p class="lead">
          识别 · 校正 · 导出 · 训练 · 切换——五步飞轮
          <el-tag v-if="detectorTag" :type="detectorTag.type" size="small" class="ml-8">
            {{ detectorTag.text }}
          </el-tag>
        </p>
      </div>
      <el-button type="primary" @click="go('/detect')">开始识别</el-button>
    </header>

    <!-- 顶部统计卡 -->
    <div class="stats-grid">
      <div class="stat-card accent" @click="go('/detect')">
        <div class="label">识别目标</div>
        <div class="value">{{ stats?.totals.detections ?? 0 }}</div>
        <div class="sub">今日 +{{ stats?.today.detections ?? 0 }}</div>
      </div>
      <div class="stat-card" @click="go('/annotate')">
        <div class="label">校正动作</div>
        <div class="value">{{ stats?.totals.corrections ?? 0 }}</div>
        <div class="sub">今日 +{{ stats?.today.corrections ?? 0 }}</div>
      </div>
      <div class="stat-card" @click="go('/dataset')">
        <div class="label">训练集</div>
        <div class="value">{{ stats?.totals.datasets ?? 0 }}</div>
        <div class="sub">已导出版本</div>
      </div>
      <div class="stat-card" @click="go('/dataset')">
        <div class="label">模型权重</div>
        <div class="value">{{ stats?.totals.weights ?? 0 }}</div>
        <div class="sub">含训练产出</div>
      </div>
      <div class="stat-card warn" @click="go('/annotate')">
        <div class="label">待处理工单</div>
        <div class="value">{{ stats?.totals.open_tickets ?? 0 }}</div>
        <div class="sub">需管理员跟进</div>
      </div>
      <div class="stat-card">
        <div class="label">平均置信度</div>
        <div class="value">{{ ((stats?.avg_confidence ?? 0) * 100).toFixed(1) }}%</div>
        <div class="sub">全量检测</div>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中…</div>

    <template v-else-if="stats">
      <!-- 图表区 -->
      <div class="chart-grid">
        <div class="card">
          <BarChart :data="classChartData" title="类别分布（Top 10）" color="#1976d2" />
        </div>
        <div class="card">
          <BarChart :data="actionChartData" title="校正动作分布" color="#2e7d32" />
        </div>
        <div class="card">
          <BarChart :data="detectTrendData" title="识别趋势（近 14 天）" color="#f57c00" />
        </div>
        <div class="card">
          <BarChart :data="corrTrendData" title="校正趋势（近 14 天）" color="#7b1fa2" />
        </div>
      </div>

      <!-- 状态分布 + 最近活动 -->
      <div class="lower-grid">
        <div class="card">
          <h3>检测状态分布</h3>
          <div class="status-list">
            <div v-for="row in statusRows" :key="row.label" class="status-row">
              <span class="status-label">{{ statusLabel[row.label] ?? row.label }}</span>
              <div class="bar-wrap">
                <div class="bar-fill" :style="{ width: `${row.percent}%` }" />
              </div>
              <span class="status-count">{{ row.value }}</span>
            </div>
            <el-empty v-if="!statusRows.length" description="暂无检测" :image-size="60" />
          </div>

          <h3 style="margin-top: 18px">系统状态</h3>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="版本">{{ health?.version }}</el-descriptions-item>
            <el-descriptions-item label="数据库">
              <el-tag size="small" :type="health?.db === 'ok' ? 'success' : 'danger'">
                {{ health?.db }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="检测器">
              <el-tag size="small" :type="detectorTag?.type">{{ health?.detector_mode }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="用户数">{{ health?.user_count }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="card">
          <h3>最近识别</h3>
          <el-table :data="stats.recent_tasks" size="small" max-height="180">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="type" label="类型" width="80" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small">{{ statusLabel[row.status] ?? row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detections" label="目标数" width="90" />
          </el-table>

          <h3 style="margin-top: 18px">最近校正</h3>
          <el-table :data="stats.recent_corrections" size="small" max-height="180">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="action" label="动作" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.action === 'undo' ? 'warning' : 'info'">
                  {{ actionLabel[row.action] ?? row.action }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detection_id" label="检测" width="80" />
            <el-table-column prop="operator" label="操作人" width="110" />
          </el-table>
        </div>
      </div>

      <!-- 快捷入口 -->
      <div class="card quick">
        <h3>快捷入口</h3>
        <div class="quick-grid">
          <el-button @click="go('/detect')">上传识别</el-button>
          <el-button @click="go('/annotate')">校正工作台</el-button>
          <el-button @click="go('/dataset')">导出训练集</el-button>
          <el-button @click="go('/dataset')">管理权重</el-button>
          <el-button v-if="auth.isAdmin" @click="go('/admin')">系统管理</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 18px;
  gap: 16px;
}
.hero h2 {
  margin: 0 0 4px;
  font-size: 22px;
}
.lead {
  margin: 0;
  color: var(--vf-ink-muted);
  display: flex;
  align-items: center;
}
.ml-8 {
  margin-left: 8px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.stat-card {
  background: var(--vf-surface);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg);
  padding: 14px 16px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.stat-card:hover {
  border-color: var(--vf-accent);
  transform: translateY(-1px);
}
.stat-card.accent {
  background: var(--vf-accent-soft);
  border-color: var(--vf-accent);
}
.stat-card.warn {
  background: #fff8e1;
  border-color: #f57c00;
}
.stat-card .label {
  color: var(--vf-ink-muted);
  font-size: 12px;
}
.stat-card .value {
  font-size: 26px;
  font-weight: 700;
  margin: 4px 0;
}
.stat-card .sub {
  color: var(--vf-ink-muted);
  font-size: 11px;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.lower-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 12px;
  margin-bottom: 12px;
}
.card {
  background: var(--vf-surface);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg);
  padding: 14px;
}
.card h3 {
  margin: 0 0 10px;
  font-size: 13px;
}
.status-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.status-row {
  display: grid;
  grid-template-columns: 80px 1fr 60px;
  gap: 8px;
  align-items: center;
  font-size: 12px;
}
.status-label {
  color: var(--vf-ink-muted);
}
.bar-wrap {
  height: 8px;
  background: var(--vf-bg);
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: var(--vf-accent);
  border-radius: 4px;
}
.status-count {
  text-align: right;
  font-weight: 600;
}
.quick-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.loading {
  padding: 32px;
  color: var(--vf-ink-muted);
  text-align: center;
}
@media (max-width: 900px) {
  .lower-grid {
    grid-template-columns: 1fr;
  }
}
</style>
