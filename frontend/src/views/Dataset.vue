<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  cancelTraining,
  compareWeights,
  datasetDownload,
  datasetExport,
  datasetHoldout,
  datasetList,
  datasetPending,
  deleteWeight,
  getTraining,
  listTraining,
  listWeights,
  rollbackWeight,
  setDefaultWeight,
  startTraining,
  uploadWeight,
  weightHistory,
} from '@/api/dataset'
import type { DatasetExportRow, DatasetPending, DatasetSample, TrainRun, Weight, WeightComparison, WeightSnapshot } from '@/api/dataset'
import AppCard from '@/components/AppCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SkeletonBlock from '@/components/SkeletonBlock.vue'
import StatCard from '@/components/StatCard.vue'
import { usePermissions } from '@/composables/usePermissions'

const pending = ref<DatasetPending | null>(null)
const exports = ref<DatasetExportRow[]>([])
const holdout = ref<DatasetSample[]>([])
const weights = ref<Weight[]>([])
const runs = ref<TrainRun[]>([])
const loading = ref(true)
const { can } = usePermissions()
const activeTab = ref<'dataset' | 'weights' | 'train'>('dataset')

const exportForm = reactive({ name: '', valRatio: 0.2 })
const trainForm = reactive({
  datasetVersion: '',
  baseWeight: 'yolov8n.pt',
  epochs: 100,
  imgsz: 640,
  batch: 16,
})

const canExport = computed(() => (pending.value?.pending_images ?? 0) > 0)
const defaultWeight = computed(() => weights.value.find((w) => w.is_default))

// ---- Model comparison (AI-1) ----
const compareOpen = ref(false)
const compareBase = ref<number | null>(null)
const compareTarget = ref<number | null>(null)
const comparison = ref<WeightComparison | null>(null)
const history = ref<WeightSnapshot[]>([])
const compareLoading = ref(false)

async function openCompare() {
  compareOpen.value = true
  history.value = await weightHistory().catch(() => [])
  if (history.value.length >= 2) {
    compareBase.value = history.value[0].id
    compareTarget.value = history.value[1].id
    await runCompare()
  }
}

async function runCompare() {
  if (!compareBase.value || !compareTarget.value) return
  compareLoading.value = true
  try {
    comparison.value = await compareWeights(compareBase.value, compareTarget.value)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '对比失败')
  } finally {
    compareLoading.value = false
  }
}

async function onRollback(id: number) {
  try {
    await ElMessageBox.confirm('回滚到该权重？（热切换，不重启）', '⚠ 确认', {
      type: 'warning',
      confirmButtonText: '回滚',
      cancelButtonText: '取消',
    })
    const r = await rollbackWeight(id)
    ElMessage.success(`✓ 已回滚到 ${r.filename}（${r.reloaded_in_ms.toFixed(0)}ms）`)
    await refresh()
    compareOpen.value = false
  } catch {
    /* cancelled */
  }
}
const trainingCount = computed(() => runs.value.filter((r) => r.status === 'running' || r.status === 'pending').length)

const statusType: Record<string, 'chip-success' | 'chip-warning' | 'chip-danger' | 'chip-primary' | 'chip-neutral'> = {
  exporting: 'chip-primary',
  done: 'chip-success',
  failed: 'chip-danger',
  pending: 'chip-neutral',
  running: 'chip-warning',
  cancelled: 'chip-neutral',
}

async function refresh() {
  loading.value = true
  try {
    const [p, e, h, w, r] = await Promise.all([
      datasetPending(),
      datasetList(1, 20),
      datasetHoldout(1, 20),
      listWeights(),
      listTraining(1, 20),
    ])
    pending.value = p
    exports.value = e.items
    holdout.value = h.items
    weights.value = w
    runs.value = r.items
    if (!trainForm.datasetVersion && exports.value.length > 0) {
      trainForm.datasetVersion = exports.value[0].dataset_version
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function onExport() {
  try {
    const result = await datasetExport({
      name: exportForm.name || undefined,
      val_ratio: exportForm.valRatio,
    })
    ElMessage.success(`◈ 已导出 ${result.dataset_version}（train ${result.train_images} / val ${result.val_images}）`)
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导出失败')
  }
}

async function onDownload(row: DatasetExportRow) {
  try {
    const blob = await datasetDownload(row.dataset_version)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${row.dataset_version}.zip`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '下载失败')
  }
}

async function onUploadWeight(file: File) {
  try {
    await uploadWeight(file)
    ElMessage.success('❖ 权重已上传')
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '上传失败')
  }
}

function pickWeight() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pt,.onnx,.engine'
  input.onchange = () => {
    const f = input.files?.[0]
    if (f) void onUploadWeight(f)
  }
  input.click()
}

async function onSetDefault(w: Weight) {
  try {
    const res = await setDefaultWeight(w.id)
    ElMessage.success(`✓ 已切换默认权重 ${res.filename}（热加载 ${res.reloaded_in_ms.toFixed(0)}ms，无需重启）`)
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '切换失败')
  }
}

async function onDeleteWeight(w: Weight) {
  try {
    await ElMessageBox.confirm(`删除权重 ${w.filename}？此操作不可逆。`, '⚠ 确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await deleteWeight(w.id)
    ElMessage.success('已删除')
    await refresh()
  } catch {
    /* cancelled */
  }
}

async function onTrain() {
  if (!trainForm.datasetVersion) {
    ElMessage.warning('请先选择数据集')
    return
  }
  try {
    const run = await startTraining({
      dataset_version: trainForm.datasetVersion,
      base_weight: trainForm.baseWeight,
      epochs: trainForm.epochs,
      imgsz: trainForm.imgsz,
      batch: trainForm.batch,
    })
    ElMessage.success(`✓ 训练任务 #${run.id} 已启动`)
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '启动失败')
  }
}

async function onCancelRun(run: TrainRun) {
  await cancelTraining(run.id)
  await refresh()
}

async function pollRun(run: TrainRun) {
  const fresh = await getTraining(run.id)
  const idx = runs.value.findIndex((r) => r.id === run.id)
  if (idx >= 0) runs.value[idx] = fresh
}

function classList(row: DatasetExportRow): string[] {
  try {
    return JSON.parse(row.class_names)
  } catch {
    return []
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader
      title="数据与权重"
      subtitle="把校正结果导出成 YOLO 训练集，触发训练，然后把训好的权重切回线上——飞轮转一圈。"
      :breadcrumb="[{ text: '控制台', to: '/dashboard' }, { text: '数据与权重' }]"
    >
      <template #actions>
        <el-button v-if="can('dataset.export')" type="primary" size="large" :disabled="!canExport" @click="onExport">
          ◈ 导出训练集
        </el-button>
        <el-button v-if="can('weight.write')" size="large" @click="pickWeight">❖ 上传权重</el-button>
      </template>
    </PageHeader>

    <!-- 顶部统计 -->
    <div class="stats-grid">
      <template v-if="loading">
        <div v-for="i in 4" :key="i" class="stat-skeleton">
          <SkeletonBlock :lines="1" height="14px" width="55%" />
          <SkeletonBlock :lines="1" height="32px" width="75%" />
        </div>
      </template>
      <template v-else>
        <StatCard
          label="待导出图片"
          :value="pending?.pending_images ?? 0"
          accent="primary"
          icon="↑"
          hint="已校正未导出"
        />
        <StatCard
          label="冻结评估集"
          :value="pending?.holdout_images ?? 0"
          accent="warning"
          icon="⚑"
          hint="永不参与训练"
        />
        <StatCard
          label="已导出版本"
          :value="exports.length"
          accent="neutral"
          icon="◈"
        />
        <StatCard
          label="训练进行中"
          :value="trainingCount"
          accent="success"
          icon="▶"
          :hint="trainingCount > 0 ? '点击训练标签查看' : '暂无训练任务'"
        />
      </template>
    </div>

    <el-tabs v-model="activeTab">
      <!-- 数据集 -->
      <el-tab-pane :label="`数据集 (${exports.length})`" name="dataset">
        <AppCard title="导出设置" subtitle="生成 ultralytics 标准格式">
          <div class="export-form">
            <div class="field">
              <label class="field-label">数据集名称（可选）</label>
              <el-input v-model="exportForm.name" placeholder="例如 factory_v2" size="large" />
            </div>
            <div class="field">
              <label class="field-label">验证集比例</label>
              <el-input-number
                v-model="exportForm.valRatio"
                :min="0.05"
                :max="0.5"
                :step="0.05"
                size="large"
                style="width: 100%"
              />
            </div>
            <el-button v-if="can('dataset.export')" type="primary" size="large" :disabled="!canExport" @click="onExport">
              ◈ 导出训练集
            </el-button>
            <p v-if="!canExport" class="hint">没有待导出的校正样本。去「校正工作台」修正检测后再回来。</p>
          </div>
        </AppCard>

        <AppCard title="导出历史" class="mt-3">
          <el-table v-if="exports.length" :data="exports" size="default">
            <el-table-column label="版本" min-width="220">
              <template #default="{ row }">
                <code class="mono">{{ row.dataset_version }}</code>
              </template>
            </el-table-column>
            <el-table-column label="规模" width="180">
              <template #default="{ row }">
                <div class="num">
                  train {{ row.train_images }} · val {{ row.val_images }}
                </div>
                <div class="text-subtle num">holdout {{ row.holdout_images }}</div>
              </template>
            </el-table-column>
            <el-table-column label="类别" min-width="200">
              <template #default="{ row }">
                <div class="chip-list">
                  <span v-for="c in classList(row)" :key="c" class="chip chip-primary">{{ c }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <span class="chip" :class="statusType[row.status]">{{ row.status }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="onDownload(row)">下载 zip</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            title="还没有导出版本"
            description="校正完样本后点「导出训练集」"
            icon="◈"
          />
        </AppCard>

        <AppCard title="冻结评估集" subtitle="永不参与训练 · 用作 mAP 基线" class="mt-3">
          <el-table v-if="holdout.length" :data="holdout" size="default" max-height="280">
            <el-table-column prop="image_path" label="图片" min-width="320">
              <template #default="{ row }">
                <code class="mono">{{ row.image_path }}</code>
              </template>
            </el-table-column>
            <el-table-column label="冻结" width="100">
              <template #default="{ row }">
                <span v-if="row.is_frozen" class="chip chip-warning">已冻结</span>
                <span v-else class="chip chip-neutral">未冻结</span>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            title="暂无评估集"
            description="首次导出时会自动抽出 10% 作为 holdout"
            icon="⚑"
            size="sm"
          />
        </AppCard>
      </el-tab-pane>

      <!-- 权重 -->
      <el-tab-pane :label="`权重 (${weights.length})`" name="weights">
        <AppCard title="权重管理" subtitle="切换默认权重立即生效，无需重启">
          <template #actions>
            <el-button v-if="can('weight.write')" type="primary" @click="pickWeight">❖ 上传 .pt 权重</el-button>
            <el-button @click="openCompare">⚖ 版本对比</el-button>
            <span v-if="defaultWeight" class="current-weight">
              当前默认：
              <code class="mono">{{ defaultWeight.filename }}</code>
            </span>
          </template>

          <el-table v-if="weights.length" :data="weights" size="default">
            <el-table-column label="文件名" min-width="220">
              <template #default="{ row }">
                <code class="mono">{{ row.filename }}</code>
              </template>
            </el-table-column>
            <el-table-column label="来源" width="120">
              <template #default="{ row }">
                <span class="chip" :class="row.source === 'trained' ? 'chip-success' : 'chip-neutral'">
                  {{ row.source === 'trained' ? '训练产出' : '手动上传' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="数据集" min-width="200">
              <template #default="{ row }">
                <code class="mono">{{ row.dataset_version ?? '—' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="mAP" width="100" align="right">
              <template #default="{ row }">
                <span class="num">{{ row.holdout_map != null ? row.holdout_map.toFixed(3) : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span v-if="row.is_default" class="chip chip-success">默认</span>
                <span v-else class="chip chip-neutral">备用</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button size="small" text type="primary" :disabled="row.is_default" @click="onSetDefault(row)">
                  切换为默认
                </el-button>
                <el-button size="small" text type="danger" :disabled="row.is_default" @click="onDeleteWeight(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            title="暂无权重"
            description="上传 .pt 或从训练产出"
            icon="❖"
            action-text="上传"
            @action="pickWeight"
          />

          <el-alert type="info" :closable="false" show-icon class="mt-4">
            <template #title>权重热切换（PRD G4）</template>
            <template #default>
              切换默认权重立即生效，不重启服务。记录 <code class="mono">holdout_map</code> 作为质量基线。
            </template>
          </el-alert>
        </AppCard>
      </el-tab-pane>

      <!-- 训练 -->
      <el-tab-pane :label="`训练 (${runs.length})`" name="train">
        <AppCard title="启动训练" subtitle="基于导出的数据集">
          <div class="train-form">
            <div class="field">
              <label class="field-label">数据集</label>
              <el-select v-model="trainForm.datasetVersion" size="large" style="width: 100%">
                <el-option
                  v-for="e in exports"
                  :key="e.dataset_version"
                  :value="e.dataset_version"
                  :label="`${e.dataset_version} (train ${e.train_images} / val ${e.val_images})`"
                />
              </el-select>
            </div>
            <div class="form-grid">
              <div class="field">
                <label class="field-label">基础权重</label>
                <el-input v-model="trainForm.baseWeight" size="large" />
              </div>
              <div class="field">
                <label class="field-label">epochs</label>
                <el-input-number v-model="trainForm.epochs" :min="1" :max="1000" size="large" style="width: 100%" />
              </div>
              <div class="field">
                <label class="field-label">imgsz</label>
                <el-input-number v-model="trainForm.imgsz" :min="128" :max="2048" :step="32" size="large" style="width: 100%" />
              </div>
              <div class="field">
                <label class="field-label">batch</label>
                <el-input-number v-model="trainForm.batch" :min="1" :max="256" size="large" style="width: 100%" />
              </div>
            </div>
            <el-button v-if="can('train.write')" type="primary" size="large" @click="onTrain">▶ 启动训练</el-button>
          </div>
        </AppCard>

        <AppCard title="训练记录" class="mt-3">
          <el-table v-if="runs.length" :data="runs" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column label="数据集" min-width="200">
              <template #default="{ row }">
                <code class="mono">{{ row.dataset_version }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="base_weight" label="基础权重" width="140" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <span class="chip" :class="statusType[row.status]">{{ row.status }}</span>
              </template>
            </el-table-column>
            <el-table-column label="进度" width="160">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round(row.progress * 100)"
                  :stroke-width="6"
                  :status="row.status === 'failed' ? 'exception' : row.status === 'done' ? 'success' : undefined"
                />
              </template>
            </el-table-column>
            <el-table-column label="mAP" width="100" align="right">
              <template #default="{ row }">
                <span class="num">{{ row.holdout_map != null ? row.holdout_map.toFixed(3) : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button
                  size="small"
                  text
                  type="warning"
                  :disabled="!['pending', 'running'].includes(row.status)"
                  @click="onCancelRun(row)"
                >
                  取消
                </el-button>
                <el-button size="small" text type="primary" @click="pollRun(row)">刷新</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            title="还没有训练任务"
            description="选择数据集后启动训练"
            icon="▶"
          />

          <el-alert type="warning" :closable="false" show-icon class="mt-4">
            <template #title>训练依赖（ADR-002）</template>
            <template #default>
              训练需要 ultralytics（<code class="mono">pip install -r requirements-ml.txt</code>）。
              降级检测器模式下禁止训练。
            </template>
          </el-alert>
        </AppCard>
      </el-tab-pane>
    </el-tabs>

    <!-- 模型版本对比对话框 (AI-1) -->
    <el-dialog v-model="compareOpen" title="⚖ 模型版本对比" width="720">
      <div class="compare-form">
        <div class="compare-picker">
          <div class="field">
            <label class="field-label">基准权重</label>
            <el-select v-model="compareBase" size="large" style="width: 100%">
              <el-option v-for="w in history" :key="w.id" :value="w.id" :label="`${w.filename} (id=${w.id})`" />
            </el-select>
          </div>
          <div class="field">
            <label class="field-label">对比权重</label>
            <el-select v-model="compareTarget" size="large" style="width: 100%">
              <el-option v-for="w in history" :key="w.id" :value="w.id" :label="`${w.filename} (id=${w.id})`" />
            </el-select>
          </div>
          <el-button type="primary" :loading="compareLoading" @click="runCompare">对比</el-button>
        </div>

        <div v-if="comparison" class="compare-result">
          <el-table :data="[comparison.base, comparison.target]" size="default">
            <el-table-column label="属性" width="160">
              <template #default="scope">
                <div class="compare-label">{{ ['基准', '对比'][scope.$index] }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="filename" label="文件" min-width="200" />
            <el-table-column label="holdout mAP" width="130" align="right">
              <template #default="{ row }">
                <span class="num">{{ row.holdout_map != null ? row.holdout_map.toFixed(4) : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="dataset_version" label="训练集" min-width="180" />
            <el-table-column prop="class_count" label="类别" width="80" align="right" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span v-if="row.is_default" class="chip chip-success">默认</span>
                <span v-else class="chip chip-neutral">备用</span>
              </template>
            </el-table-column>
          </el-table>

          <div class="compare-delta">
            <div class="compare-delta__title">差异</div>
            <div class="compare-delta__row">
              <span>holdout mAP 变化：</span>
              <span
                v-if="comparison.delta.holdout_map != null"
                class="num"
                :class="comparison.delta.improved ? 'text-success' : comparison.delta.regressed ? 'text-danger' : ''"
              >
                {{ comparison.delta.holdout_map >= 0 ? '+' : '' }}{{ comparison.delta.holdout_map.toFixed(4) }}
                {{ comparison.delta.improved ? '(改进)' : comparison.delta.regressed ? '(回退)' : '(持平)' }}
              </span>
              <span v-else class="text-subtle">无法比较</span>
            </div>
            <div class="compare-delta__row">
              <span>同源训练集：</span>
              <span>{{ comparison.delta.same_dataset ? '✓' : '✗' }}</span>
            </div>
            <div class="compare-delta__row">
              <span>类别数一致：</span>
              <span>{{ comparison.delta.same_classes ? '✓' : '✗' }}</span>
            </div>
          </div>

          <div class="compare-actions">
            <el-button type="warning" @click="onRollback(comparison.target.id)">⚠ 回滚到对比权重</el-button>
            <el-button type="warning" plain @click="onRollback(comparison.base.id)">回滚到基准权重</el-button>
          </div>
        </div>

        <el-empty v-else-if="!compareLoading && history.length < 2" description="至少需要 2 个权重才能对比" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.mt-3 { margin-top: var(--sp-3); }
.mt-4 { margin-top: var(--sp-4); }

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

.export-form, .train-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--sp-3);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.field-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
  color: var(--text-secondary);
}
.hint {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}

.chip-list {
  display: flex;
  gap: var(--sp-1);
  flex-wrap: wrap;
}
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

.current-weight {
  margin-left: var(--sp-3);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
</style>
