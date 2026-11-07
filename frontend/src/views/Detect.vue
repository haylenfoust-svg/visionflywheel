<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { batchUpload, uploadAndDetect } from '@/api/tasks'
import AppCard from '@/components/AppCard.vue'
import AiInsightCard from '@/components/AiInsightCard.vue'
import DetectionTable from '@/components/DetectionTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SkeletonBlock from '@/components/SkeletonBlock.vue'
import UploadDrop from '@/components/UploadDrop.vue'
import { usePermissions } from '@/composables/usePermissions'
import type { Detection, UploadResult } from '@/types/detection'

const { can } = usePermissions()

const params = reactive({
  conf_threshold: 0.5,
  iou_threshold: 0.45,
  imgsz: 640,
})

const loading = ref(false)
const result = ref<UploadResult | null>(null)
const selected = ref<Detection | null>(null)
const previewUrl = ref<string>('')
const batchProgress = ref<{ done: number; total: number } | null>(null)
const recentBatch = ref<Array<{ taskId: number }>>([])

const avgConfidence = computed(() => {
  if (!result.value?.detections?.length) return null
  const total = result.value.detections.reduce((s, d) => s + d.confidence, 0)
  return total / result.value.detections.length
})

const confRange = computed(() => {
  const dets = result.value?.detections ?? []
  if (!dets.length) return null
  const confs = dets.map((d) => d.confidence)
  return {
    min: Math.min(...confs),
    max: Math.max(...confs),
    suggested: avgConfidence.value ?? 0,
  }
})

const aiRationale = computed(() => {
  const dets = result.value?.detections ?? []
  if (!dets.length) return '未检测到目标。可以尝试调低置信度阈值或换一张图片。'
  const byClass = dets.reduce<Record<string, number>>((acc, d) => {
    const k = d.class_name_zh || d.class_name
    acc[k] = (acc[k] ?? 0) + 1
    return acc
  }, {})
  const top = Object.entries(byClass).sort((a, b) => b[1] - a[1])[0]
  return `主要类别为「${top[0]}」，共 ${top[1]} 个目标。平均置信度 ${((avgConfidence.value ?? 0) * 100).toFixed(1)}%，${dets.length >= 5 ? '目标较多，建议逐个校正。' : '数量较少，可直接进入校正工作台。'}`
})

const aiSources = computed(() => {
  const s: Array<{ label: string; type?: 'model' | 'rule' | 'kb' }> = []
  if (result.value?.detector_mode === 'yolo') s.push({ label: 'YOLO', type: 'model' })
  else s.push({ label: '降级检测器', type: 'rule' })
  s.push({ label: '实时推理', type: 'model' })
  return s
})

// ---- Drawer detail (UI改进6) ----
const showDetailDrawer = ref(false)

function openDetail() {
  if (selected.value) showDetailDrawer.value = true
}

// ---- Recognition history (UI改进6) ----
const recognitionHistory = ref<Array<{ id: number; name: string; count: number; url: string; ts: string }>>([])
const showHistory = ref(false)

function addToHistory(res: UploadResult, filename: string) {
  recognitionHistory.value.unshift({
    id: res.task_id,
    name: filename,
    count: res.detections.length,
    url: res.result_url || res.image_url,
    ts: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  })
  if (recognitionHistory.value.length > 12) recognitionHistory.value.pop()
}

function useHistoryItem(item: { url: string }) {
  previewUrl.value = item.url
  showHistory.value = false
  ElMessage.success('已载入历史结果')
}

// ---- URL state sync (UI改进6) ----
function syncUrlToState() {
  const u = new URL(window.location.href)
  if (result.value?.task_id) u.searchParams.set('task', String(result.value.task_id))
  if (params.conf_threshold !== 0.5) u.searchParams.set('conf', String(params.conf_threshold))
  if (params.iou_threshold !== 0.45) u.searchParams.set('iou', String(params.iou_threshold))
  window.history.replaceState({}, '', u.toString())
}

function loadUrlState() {
  const u = new URL(window.location.href)
  const conf = u.searchParams.get('conf')
  const iou = u.searchParams.get('iou')
  if (conf) params.conf_threshold = parseFloat(conf)
  if (iou) params.iou_threshold = parseFloat(iou)
}

onMounted(loadUrlState)

const detectorTag = computed(() => {
  const mode = result.value?.detector_mode
  if (mode === 'yolo') return { text: 'YOLO 引擎', type: 'success' as const, icon: '⚡' }
  if (mode === 'fallback') return { text: '降级检测器', type: 'warning' as const, icon: '🛡' }
  return null
})

const classDistribution = computed(() => {
  if (!result.value) return []
  const map = new Map<string, number>()
  for (const d of result.value.detections) {
    const name = d.class_name_zh || d.class_name
    map.set(name, (map.get(name) ?? 0) + 1)
  }
  return Array.from(map.entries()).map(([name, count]) => ({ name, count }))
})

async function onFile(file: File) {
  if (loading.value) return
  loading.value = true
  selected.value = null
  try {
    const res = await uploadAndDetect(file, {
      conf_threshold: params.conf_threshold,
      iou_threshold: params.iou_threshold,
      imgsz: params.imgsz,
    })
    result.value = res
    previewUrl.value = res.result_url || res.image_url
    if (res.detector_mode === 'fallback') {
      ElMessage.warning('当前使用降级检测器。闭环可跑通，但精度有限。')
    } else {
      ElMessage.success(`识别完成，共 ${res.detections.length} 个目标`)
    addToHistory(res, file.name)
    syncUrlToState()
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '识别失败')
  } finally {
    loading.value = false
  }
}

async function onBatch(files: File[]) {
  if (loading.value || files.length === 0) return
  if (files.length === 1) return onFile(files[0])
  loading.value = true
  batchProgress.value = { done: 0, total: files.length }
  try {
    const res = await batchUpload(files, {
      conf_threshold: params.conf_threshold,
      iou_threshold: params.iou_threshold,
      imgsz: params.imgsz,
    })
    batchProgress.value = { done: res.total_items, total: files.length }
    recentBatch.value = res.task_ids.slice(0, 6).map((id) => ({ taskId: id }))
    ElMessage.success(`批量识别完成：${res.total_items} 个任务`)
    if (res.status === 'partial') ElMessage.warning('部分图片识别失败')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '批量识别失败')
  } finally {
    loading.value = false
    batchProgress.value = null
  }
}

function onSelectDetection(d: Detection) {
  selected.value = d
}

function reset() {
  result.value = null
  selected.value = null
  previewUrl.value = ''
}
</script>

<template>
  <div class="page">
    <PageHeader
      title="识别"
      subtitle="上传图片，实时看模型框出什么。看错了就去「校正工作台」修改——每次修正都会让模型更强。"
      :breadcrumb="[{ text: '控制台', to: '/dashboard' }, { text: '识别' }]"
    >
      <template #actions>
        <el-tag v-if="detectorTag" :type="detectorTag.type" size="large" effect="light" round>
          {{ detectorTag.icon }} {{ detectorTag.text }}
        </el-tag>
        <el-button v-if="recognitionHistory.length" size="large" @click="showHistory = true">
          ⏱ 识别历史 ({{ recognitionHistory.length }})
        </el-button>
        <el-button v-if="result" size="large" @click="reset">重新开始</el-button>
      </template>
    </PageHeader>

    <!-- 降级模式提示 -->
    <el-alert
      v-if="detectorTag?.type === 'warning'"
      type="warning"
      :closable="false"
      show-icon
      class="mb-6"
    >
      <template #title>
        <strong>降级检测器已启用</strong>
        <span class="ml-2">
          未检测到 ultralytics/torch，已切到规则检测器。闭环可跑通，精度有限。
          安装 <code class="mono">pip install -r requirements-ml.txt</code> 可切回真实 YOLO。
        </span>
      </template>
    </el-alert>

    <div class="grid">
      <!-- 左侧：上传 + 参数 -->
      <aside class="sidebar">
        <AppCard title="上传" subtitle="支持多选拖拽" hoverable>
          <UploadDrop
v-if="can('task.write')" :disabled="loading"
            :multiple="true"
            @select="onFile"
            @select-many="onBatch"
          />

          <div v-if="batchProgress" class="batch-progress">
            <div class="batch-progress__label">
              批量识别中
              <span class="num">{{ batchProgress.done }} / {{ batchProgress.total }}</span>
            </div>
            <el-progress
              :percentage="Math.round((batchProgress.done / batchProgress.total) * 100)"
              :stroke-width="8"
              :show-text="false"
            />
          </div>

          <div v-if="recentBatch.length" class="recent-batch">
            <div class="recent-batch__label">最近批量任务</div>
            <div class="recent-batch__list">
              <span v-for="t in recentBatch" :key="t.taskId" class="chip chip-neutral">
                #{{ t.taskId }}
              </span>
            </div>
          </div>
        </AppCard>

        <AppCard title="推理参数" subtitle="实时生效">
          <div class="params">
            <div class="param-row">
              <div class="param-head">
                <label class="param-label">置信度阈值</label>
                <span class="param-value num">{{ params.conf_threshold.toFixed(2) }}</span>
              </div>
              <el-slider
                v-model="params.conf_threshold"
                :min="0"
                :max="1"
                :step="0.05"
                :show-tooltip="false"
              />
              <div class="param-hint">宁可错杀调低，避免噪声调高</div>
            </div>

            <div class="param-row">
              <div class="param-head">
                <label class="param-label">IoU 阈值</label>
                <span class="param-value num">{{ params.iou_threshold.toFixed(2) }}</span>
              </div>
              <el-slider
                v-model="params.iou_threshold"
                :min="0"
                :max="1"
                :step="0.05"
                :show-tooltip="false"
              />
              <div class="param-hint">重叠框抑制强度</div>
            </div>

            <div class="param-row">
              <div class="param-head">
                <label class="param-label">推理尺寸</label>
              </div>
              <el-select v-model="params.imgsz" size="default" class="param-select">
                <el-option :value="320" label="320 · 快速" />
                <el-option :value="640" label="640 · 平衡" />
                <el-option :value="960" label="960 · 精细" />
                <el-option :value="1280" label="1280 · 精细" />
              </el-select>
            </div>
          </div>
        </AppCard>
      </aside>

      <!-- 右侧：结果 -->
      <section class="content">
        <!-- 加载骨架 -->
        <AppCard v-if="loading" title="识别中">
          <div class="loading-state">
            <SkeletonBlock variant="block" height="360px" />
            <SkeletonBlock :lines="3" height="14px" class="mt-4" />
          </div>
        </AppCard>

        <!-- 空态 -->
        <AppCard v-else-if="!result">
          <EmptyState
            title="还没有识别结果"
            description="拖一张图片到左侧开始识别。也可以一次拖多张做批量识别。"
            icon="◎"
            size="lg"
          />
        </AppCard>

        <!-- 结果 -->
        <template v-else>
          <AppCard title="识别结果" class="result-card">
            <template #actions>
              <div class="result-meta">
                <span class="chip chip-primary">任务 #{{ result.task_id }}</span>
                <span class="chip chip-neutral num">{{ result.inference_ms.toFixed(0) }}ms</span>
                <span class="chip chip-success">{{ result.detections.length }} 个目标</span>
              </div>
            </template>

            <div class="preview">
              <img v-if="previewUrl" :src="previewUrl" alt="识别结果" class="preview__img" />
              <div v-else class="preview__empty">无结果图</div>
            </div>

            <!-- AI 智能分析卡 -->
            <AiInsightCard
              title="AI 识别分析"
              :headline="`${result.detections.length} 个目标`"
              headline-sub="基于 YOLO 检测结果"
              :confidence="avgConfidence"
              :range="confRange"
              :rationale="aiRationale"
              :sources="aiSources"
              tone="primary"
            />

            <!-- 类别分布 -->
            <div v-if="classDistribution.length" class="class-dist">
              <div class="class-dist__title">类别分布</div>
              <div class="class-dist__list">
                <div v-for="c in classDistribution" :key="c.name" class="class-dist__item">
                  <span class="class-dist__name">{{ c.name }}</span>
                  <div class="class-dist__bar">
                    <div
                      class="class-dist__fill"
                      :style="{
                        width: `${(c.count / result.detections.length) * 100}%`,
                      }"
                    />
                  </div>
                  <span class="class-dist__count num">{{ c.count }}</span>
                </div>
              </div>
            </div>
          </AppCard>

          <AppCard title="检测明细" subtitle="点击行查看详情">
            <DetectionTable :detections="result.detections" @select="onSelectDetection" />

            <!-- 选中项详情 -->
            <transition name="slide">
              <div v-if="selected" class="detail-panel">
                <el-button type="primary" plain size="small" class="mb-3" @click="openDetail">
                  打开详情抽屉
                </el-button>
                <div class="detail-panel__header">
                  <h4>选中项详情</h4>
                  <el-button size="small" text @click="selected = null">关闭</el-button>
                </div>
                <div class="detail-grid">
                  <div class="detail-item">
                    <div class="detail-item__label">ID</div>
                    <div class="detail-item__value num">{{ selected.id }}</div>
                  </div>
                  <div class="detail-item">
                    <div class="detail-item__label">类别（中文）</div>
                    <div class="detail-item__value">
                      <span class="chip chip-primary">{{ selected.class_name_zh ?? '—' }}</span>
                    </div>
                  </div>
                  <div class="detail-item">
                    <div class="detail-item__label">类别（英文）</div>
                    <div class="detail-item__value mono">{{ selected.class_name }}</div>
                  </div>
                  <div class="detail-item">
                    <div class="detail-item__label">置信度</div>
                    <div class="detail-item__value num">{{ (selected.confidence * 100).toFixed(1) }}%</div>
                  </div>
                  <div class="detail-item">
                    <div class="detail-item__label">坐标 (x1, y1, x2, y2)</div>
                    <div class="detail-item__value mono">
                      {{ selected.bbox.x1.toFixed(0) }}, {{ selected.bbox.y1.toFixed(0) }},
                      {{ selected.bbox.x2.toFixed(0) }}, {{ selected.bbox.y2.toFixed(0) }}
                    </div>
                  </div>
                  <div class="detail-item">
                    <div class="detail-item__label">状态</div>
                    <div class="detail-item__value">
                      <span
                        class="chip"
                        :class="selected.status === 'corrected' ? 'chip-success' : selected.status === 'rejected' ? 'chip-danger' : 'chip-warning'"
                      >
                        {{ selected.status === 'corrected' ? '已校正' : selected.status === 'rejected' ? '已否决' : '待校正' }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </transition>
          </AppCard>
        </template>
      </section>
    </div>
    <!-- 详情抽屉 -->
    <el-drawer v-model="showDetailDrawer" title="检测详情" size="480px">
      <div v-if="selected" class="drawer-body">
        <div class="drawer-hero">
          <img v-if="previewUrl" :src="previewUrl" alt="preview" class="drawer-preview" />
        </div>
        <el-descriptions :column="1" size="default" border>
          <el-descriptions-item label="ID">{{ selected.id }}</el-descriptions-item>
          <el-descriptions-item label="类别（英文）">{{ selected.class_name }}</el-descriptions-item>
          <el-descriptions-item label="类别（中文）">{{ selected.class_name_zh ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="置信度">{{ (selected.confidence * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="坐标">
            {{ selected.bbox.x1.toFixed(0) }}, {{ selected.bbox.y1.toFixed(0) }},
            {{ selected.bbox.x2.toFixed(0) }}, {{ selected.bbox.y2.toFixed(0) }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <span class="chip" :class="selected.status === 'corrected' ? 'chip-success' : selected.status === 'rejected' ? 'chip-danger' : 'chip-warning'">
              {{ selected.status }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="来源">{{ selected.source === 'model' ? '模型' : '人工' }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-drawer>

    <!-- 识别历史抽屉 -->
    <el-drawer v-model="showHistory" title="识别历史" size="360px">
      <div v-if="recognitionHistory.length" class="history-list">
        <div
          v-for="item in recognitionHistory"
          :key="item.id"
          class="history-item"
          @click="useHistoryItem(item)"
        >
          <img :src="item.url" alt="" class="history-thumb" />
          <div class="history-body">
            <div class="history-name">{{ item.name }}</div>
            <div class="history-meta">{{ item.count }} 个目标 · {{ item.ts }}</div>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无识别历史" />
    </el-drawer>
  </div>
</template>

<style scoped>
.mb-6 { margin-bottom: var(--sp-6); }
.mt-4 { margin-top: var(--sp-4); }
.ml-2 { margin-left: var(--sp-2); }

.grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: var(--sp-3);
  align-items: start;
}
.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  position: sticky;
  top: var(--sp-4);
}
.content {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
}

/* 参数 */
.params {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}
.param-row {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.param-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.param-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
  color: var(--text-secondary);
}
.param-value {
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
  color: var(--text-accent);
  font-family: var(--font-num);
}
.param-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.param-select {
  width: 100%;
}

/* 批量进度 */
.batch-progress {
  margin-top: var(--sp-4);
}
.batch-progress__label {
  display: flex;
  justify-content: space-between;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: var(--sp-2);
}
.recent-batch {
  margin-top: var(--sp-3);
}
.recent-batch__label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-bottom: var(--sp-2);
}
.recent-batch__list {
  display: flex;
  gap: var(--sp-1);
  flex-wrap: wrap;
}

/* 加载态 */
.loading-state {
  display: flex;
  flex-direction: column;
}

/* 结果 */
.result-meta {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.preview {
  position: relative;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  overflow: hidden;
  margin-bottom: var(--sp-4);
  min-height: 200px;
}
.preview__img {
  display: block;
  width: 100%;
  max-height: 520px;
  object-fit: contain;
  animation: fade-in var(--t-base) var(--ease-decelerate);
}
.preview__empty {
  display: grid;
  place-items: center;
  min-height: 200px;
  color: var(--text-tertiary);
}

/* 类别分布 */
.class-dist {
  margin-top: var(--sp-4);
  padding-top: var(--sp-4);
  border-top: 1px solid var(--border-default);
}
.class-dist__title {
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
  color: var(--text-secondary);
  margin-bottom: var(--sp-3);
}
.class-dist__list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.class-dist__item {
  display: grid;
  grid-template-columns: 100px 1fr 60px;
  gap: var(--sp-3);
  align-items: center;
}
.class-dist__name {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.class-dist__bar {
  height: 6px;
  background: var(--bg-subtle);
  border-radius: var(--r-full);
  overflow: hidden;
}
.class-dist__fill {
  height: 100%;
  background: var(--c-primary-500);
  border-radius: var(--r-full);
  transition: width var(--t-slower) var(--ease-decelerate);
}
.class-dist__count {
  text-align: right;
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}

/* 详情面板 */
.detail-panel {
  margin-top: var(--sp-4);
  padding: var(--sp-4);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
}
.detail-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
}
.detail-panel__header h4 {
  margin: 0;
  font-size: var(--fs-md);
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-3);
}
.detail-item__label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-bottom: 2px;
}
.detail-item__value {
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

/* 转场 */
.slide-enter-active, .slide-leave-active {
  transition: all var(--t-base) var(--ease-standard);
}
.slide-enter-from, .slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.drawer-hero {
  background: var(--bg-subtle);
  border-radius: var(--r-md);
  overflow: hidden;
}
.drawer-preview {
  display: block;
  width: 100%;
  max-height: 300px;
  object-fit: contain;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.history-item {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-2);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.history-item:hover {
  border-color: var(--border-accent);
  background: var(--bg-hover);
}
.history-thumb {
  width: 64px;
  height: 48px;
  object-fit: cover;
  border-radius: var(--r-sm);
}
.history-body {
  flex: 1;
}
.history-name {
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
}
.history-meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

@media (max-width: 1000px) {
  .grid { grid-template-columns: 1fr; }
  .sidebar { position: static; }
}
</style>
