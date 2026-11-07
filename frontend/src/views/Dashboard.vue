<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { healthDetail, overview } from '@/api/stats'
import type { DashboardOverview, HealthDetail } from '@/api/stats'
import AppCard from '@/components/AppCard.vue'
import BarChart from '@/components/BarChart.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import StatCard from '@/components/StatCard.vue'
import SkeletonBlock from '@/components/SkeletonBlock.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const stats = ref<DashboardOverview | null>(null)
const health = ref<HealthDetail | null>(null)
const loading = ref(true)

const displayName = computed(() => auth.user?.display_name || auth.user?.username || '')

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
  (stats.value?.per_day ?? []).map((d) => ({ label: d.date.slice(5), value: d.count })),
)

const corrTrendData = computed(() =>
  (stats.value?.corr_per_day ?? []).map((d) => ({ label: d.date.slice(5), value: d.count })),
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

const statusLabel: Record<string, string> = {
  pending: '待校正',
  corrected: '已校正',
  rejected: '已否决',
}
const actionLabel: Record<string, string> = {
  confirm: '确认',
  relabel: '改标签',
  false_positive: '标误检',
  adjust: '改框',
  add: '补框',
  undo: '撤销',
}

const statusColor: Record<string, string> = {
  pending: 'var(--c-warning-500)',
  corrected: 'var(--c-success-500)',
  rejected: 'var(--c-danger-500)',
}

const detectorMode = computed(() => health.value?.detector_mode ?? '')
const isYolo = computed(() => detectorMode.value === 'yolo')

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
  <div class="page">
    <!-- Hero 区 -->
    <PageHeader
      :title="`欢迎回来，${displayName}`"
      subtitle="识别 · 校正 · 导出 · 训练 · 切换——五步飞轮。每一次修正都让模型更强。"
    >
      <template #actions>
        <el-tag :type="isYolo ? 'success' : 'warning'" size="large" effect="light" round>
          {{ isYolo ? 'YOLO 引擎' : '降级检测器' }}
        </el-tag>
        <el-button type="primary" size="large" @click="go('/detect')">
          开始识别
          <span class="btn-arrow">→</span>
        </el-button>
      </template>
    </PageHeader>

    <!-- 骨架屏（加载中） -->
    <div v-if="loading" class="stats-grid">
      <div v-for="i in 6" :key="i" class="stat-skeleton">
        <SkeletonBlock :lines="1" height="14px" width="60%" />
        <SkeletonBlock :lines="1" height="36px" width="80%" />
        <SkeletonBlock :lines="1" height="12px" width="50%" />
      </div>
    </div>

    <!-- 统计卡 -->
    <div v-else-if="stats" class="stats-grid">
      <StatCard
        label="识别目标"
        :value="stats.totals.detections"
        :trend="stats.today.detections"
        trend-suffix=" 今日"
        accent="primary"
        icon="◎"
        clickable
        @click="go('/detect')"
      />
      <StatCard
        label="校正动作"
        :value="stats.totals.corrections"
        :trend="stats.today.corrections"
        trend-suffix=" 今日"
        accent="success"
        icon="✎"
        clickable
        @click="go('/annotate')"
      />
      <StatCard
        label="训练集版本"
        :value="stats.totals.datasets"
        accent="neutral"
        icon="◈"
        clickable
        hint="导出的 YOLO 数据集"
        @click="go('/dataset')"
      />
      <StatCard
        label="模型权重"
        :value="stats.totals.weights"
        accent="neutral"
        icon="❖"
        clickable
        hint="含训练产出"
        @click="go('/dataset')"
      />
      <StatCard
        label="待处理工单"
        :value="stats.totals.open_tickets"
        accent="warning"
        icon="⚑"
        clickable
        hint="需管理员跟进"
        @click="go('/admin')"
      />
      <StatCard
        label="平均置信度"
        :value="`${(stats.avg_confidence * 100).toFixed(1)}%`"
        accent="neutral"
        icon="◔"
        hint="全量检测均值"
      />
    </div>

    <template v-if="stats">
      <!-- 图表区 -->
      <div class="chart-grid">
        <AppCard title="类别分布" subtitle="Top 10 · 按检测次数" hoverable>
          <BarChart :data="classChartData" color="var(--c-primary-500)" />
        </AppCard>

        <AppCard title="校正动作" subtitle="飞轮动力源 · 累计" hoverable>
          <BarChart :data="actionChartData" color="var(--c-success-500)" />
        </AppCard>

        <AppCard title="识别趋势" subtitle="近 14 天" hoverable>
          <BarChart :data="detectTrendData" color="var(--c-warning-500)" />
        </AppCard>

        <AppCard title="校正趋势" subtitle="近 14 天" hoverable>
          <BarChart :data="corrTrendData" color="var(--c-primary-400)" />
        </AppCard>
      </div>

      <!-- 状态分布 + 最近活动 -->
      <div class="lower-grid">
        <AppCard title="检测状态分布">
          <div class="status-list">
            <div
              v-for="(row, i) in statusRows"
              :key="row.label"
              class="status-row"
              :style="{ animationDelay: `${i * 80}ms` }"
            >
              <span class="status-label">
                <span
                  class="status-dot"
                  :style="{ background: statusColor[row.label] ?? 'var(--c-neutral-400)' }"
                />
                {{ statusLabel[row.label] ?? row.label }}
              </span>
              <div class="status-track">
                <div
                  class="status-fill"
                  :style="{
                    width: `${row.percent}%`,
                    background: statusColor[row.label] ?? 'var(--c-neutral-400)',
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

          <template v-if="health">
            <SectionHeader
              title="系统状态"
              description="运行时元信息"
              class="system-header"
            />
            <div class="system-grid">
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
            </div>
          </template>
        </AppCard>

        <div class="recent-stack">
          <AppCard title="最近识别" hoverable>
            <template #actions>
              <el-button size="small" text type="primary" @click="go('/detect')">查看全部</el-button>
            </template>
            <el-table
              v-if="stats.recent_tasks.length"
              :data="stats.recent_tasks"
              size="small"
              :show-header="true"
              class="recent-table"
            >
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

          <AppCard title="最近校正" hoverable>
            <template #actions>
              <el-button size="small" text type="primary" @click="go('/annotate')">进入工作台</el-button>
            </template>
            <el-table
              v-if="stats.recent_corrections.length"
              :data="stats.recent_corrections"
              size="small"
              class="recent-table"
            >
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
              <div class="quick-item__desc">用户 / 配置 / 审计</div>
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-6);
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

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

.lower-grid {
  display: grid;
  grid-template-columns: 1fr 1.25fr;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

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
  color: var(--text-primary);
}

.system-header {
  margin-top: var(--sp-6);
}
.system-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--sp-3);
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

.chip {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--sp-2);
  font-size: var(--fs-xs);
  font-weight: var(--fw-medium);
  border-radius: var(--r-full);
  letter-spacing: 0.01em;
}
.chip-primary  { color: var(--c-primary-700);  background: var(--c-primary-50); }
.chip-success  { color: var(--c-success-600);  background: var(--c-success-50); }
.chip-warning  { color: var(--c-warning-600);  background: var(--c-warning-50); }
.chip-danger   { color: var(--c-danger-600);   background: var(--c-danger-50); }
.chip-neutral  { color: var(--text-secondary);  background: var(--bg-subtle); }

.recent-stack {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.recent-table {
  margin: 0 calc(-1 * var(--sp-2));
}

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

@media (max-width: 1000px) {
  .lower-grid { grid-template-columns: 1fr; }
}
</style>
