<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  cancelTraining,
  datasetDownload,
  datasetExport,
  datasetHoldout,
  datasetList,
  datasetPending,
  deleteWeight,
  getTraining,
  listTraining,
  listWeights,
  setDefaultWeight,
  startTraining,
  uploadWeight,
} from '@/api/dataset'
import type { DatasetExportRow, DatasetPending, DatasetSample, TrainRun, Weight } from '@/api/dataset'

const pending = ref<DatasetPending | null>(null)
const exports = ref<DatasetExportRow[]>([])
const holdout = ref<DatasetSample[]>([])
const weights = ref<Weight[]>([])
const runs = ref<TrainRun[]>([])
const loading = ref(false)
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
    ElMessage.success(`已导出 ${result.dataset_version}（train ${result.train_images} / val ${result.val_images}）`)
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
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '下载失败')
  }
}

async function onUploadWeight(file: File) {
  try {
    await uploadWeight(file)
    ElMessage.success('权重已上传')
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
    ElMessage.success(
      `已切换默认权重 ${res.filename}（热加载 ${res.reloaded_in_ms.toFixed(0)}ms，无需重启）`,
    )
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '切换失败')
  }
}

async function onDeleteWeight(w: Weight) {
  try {
    await ElMessageBox.confirm(`删除权重 ${w.filename}？`, '确认', { type: 'warning' })
    await deleteWeight(w.id)
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
    ElMessage.success(`训练任务 #${run.id} 已启动`)
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

const statusType: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
  exporting: 'info',
  done: 'success',
  failed: 'danger',
  pending: 'info',
  running: 'warning',
  cancelled: 'info',
}

onMounted(refresh)
</script>

<template>
  <div class="page dataset">
    <h2>数据与权重</h2>
    <p class="lead">
      把校正结果导出成 YOLO 训练集，触发训练，然后把训好的权重切回线上——飞轮转一圈。
    </p>

    <el-tabs v-model="activeTab">
      <!-- 数据集 -->
      <el-tab-pane :label="`数据集 (${exports.length})`" name="dataset">
        <div class="stat-row">
          <div class="stat">
            <div class="label">待导出图片</div>
            <div class="value">{{ pending?.pending_images ?? 0 }}</div>
          </div>
          <div class="stat">
            <div class="label">冻结评估集</div>
            <div class="value">{{ pending?.holdout_images ?? 0 }}</div>
          </div>
          <div class="stat">
            <div class="label">已导出版本</div>
            <div class="value">{{ exports.length }}</div>
          </div>
        </div>

        <div class="toolbar">
          <el-input v-model="exportForm.name" placeholder="数据集名称（可选）" size="small" style="width: 200px" />
          <el-input-number v-model="exportForm.valRatio" :min="0.05" :max="0.5" :step="0.05" size="small" />
          <el-button type="primary" size="small" :disabled="!canExport" @click="onExport">
            导出训练集
          </el-button>
          <span v-if="!canExport" class="hint">没有待导出的校正样本</span>
        </div>

        <el-table :data="exports" size="small">
          <el-table-column prop="dataset_version" label="版本" min-width="220" />
          <el-table-column label="规模" width="160">
            <template #default="{ row }">
              <div>train {{ row.train_images }} / val {{ row.val_images }}</div>
              <div class="sub">holdout {{ row.holdout_images }}</div>
            </template>
          </el-table-column>
          <el-table-column label="类别" min-width="180">
            <template #default="{ row }">
              <el-tag v-for="c in classList(row)" :key="c" size="small" class="tag">{{ c }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType[row.status]">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="onDownload(row)">下载 zip</el-button>
            </template>
          </el-table-column>
        </el-table>

        <h3>冻结评估集（永不参与训练）</h3>
        <el-table :data="holdout" size="small" max-height="240">
          <el-table-column prop="image_path" label="图片" min-width="280" />
          <el-table-column prop="is_frozen" label="冻结" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.is_frozen" size="small" type="warning">是</el-tag>
              <span v-else>否</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 权重 -->
      <el-tab-pane :label="`权重 (${weights.length})`" name="weights">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="pickWeight">上传 .pt 权重</el-button>
          <span v-if="defaultWeight" class="hint">
            当前默认：<strong>{{ defaultWeight.filename }}</strong>
          </span>
        </div>

        <el-table :data="weights" size="small">
          <el-table-column prop="filename" label="文件名" min-width="220" />
          <el-table-column prop="source" label="来源" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.source === 'trained' ? 'success' : 'info'">
                {{ row.source === 'trained' ? '训练产出' : '手动上传' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dataset_version" label="数据集" min-width="180" />
          <el-table-column prop="holdout_map" label="mAP" width="90">
            <template #default="{ row }">
              {{ row.holdout_map != null ? row.holdout_map.toFixed(3) : '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="is_default" label="默认" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" size="small" type="success">默认</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170">
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

        <el-alert type="info" :closable="false" class="note" title="权重热切换" description="切换默认权重立即生效，不需要重启服务。这是 PRD G4 的硬性要求。" />
      </el-tab-pane>

      <!-- 训练 -->
      <el-tab-pane :label="`训练 (${runs.length})`" name="train">
        <div class="form">
          <el-form :inline="true" size="small">
            <el-form-item label="数据集">
              <el-select v-model="trainForm.datasetVersion" style="width: 260px">
                <el-option
                  v-for="e in exports"
                  :key="e.dataset_version"
                  :value="e.dataset_version"
                  :label="`${e.dataset_version} (train ${e.train_images} / val ${e.val_images})`"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="基础权重">
              <el-input v-model="trainForm.baseWeight" style="width: 160px" />
            </el-form-item>
            <el-form-item label="epochs">
              <el-input-number v-model="trainForm.epochs" :min="1" :max="1000" />
            </el-form-item>
            <el-form-item label="imgsz">
              <el-input-number v-model="trainForm.imgsz" :min="128" :max="2048" :step="32" />
            </el-form-item>
            <el-form-item label="batch">
              <el-input-number v-model="trainForm.batch" :min="1" :max="256" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="onTrain">启动训练</el-button>
            </el-form-item>
          </el-form>
        </div>

        <el-table :data="runs" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="dataset_version" label="数据集" min-width="220" />
          <el-table-column prop="base_weight" label="基础权重" width="130" />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType[row.status]">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="130">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.progress * 100)" :stroke-width="6" />
            </template>
          </el-table-column>
          <el-table-column prop="holdout_map" label="mAP" width="90">
            <template #default="{ row }">
              {{ row.holdout_map != null ? row.holdout_map.toFixed(3) : '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="error_message" label="错误" min-width="180">
            <template #default="{ row }">
              <span class="err">{{ row.error_message ?? '' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110">
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

        <el-alert type="warning" :closable="false" class="note" title="训练依赖" description="训练需要 ultralytics（pip install -r requirements-ml.txt）。降级检测器模式下禁止训练（ADR-002）。" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.lead {
  color: var(--vf-ink-muted);
}
.stat-row {
  display: grid;
  grid-template-columns: repeat(3, 180px);
  gap: 12px;
  margin-bottom: 16px;
}
.stat {
  background: var(--vf-surface);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius);
  padding: 12px;
}
.stat .label {
  font-size: 12px;
  color: var(--vf-ink-muted);
}
.stat .value {
  font-size: 22px;
  font-weight: 600;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.hint {
  color: var(--vf-ink-muted);
  font-size: 12px;
}
.sub {
  color: var(--vf-ink-muted);
  font-size: 11px;
}
.tag {
  margin-right: 4px;
}
.note {
  margin-top: 12px;
}
.err {
  color: var(--vf-danger);
  font-size: 11px;
}
.form {
  margin-bottom: 12px;
}
</style>
