<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createFeedback, createCorrection, listAudit, listFeedback, replyFeedback, undo, updateFeedbackStatus } from '@/api/corrections'
import { getTaskDetections, listTasks, uploadAndDetect } from '@/api/tasks'
import DetectionTable from '@/components/DetectionTable.vue'
import ImageAnnotator from '@/components/ImageAnnotator.vue'
import UploadDrop from '@/components/UploadDrop.vue'
import { useAuthStore } from '@/stores/auth'
import type { BBox, Detection, Task } from '@/types/detection'
import type { CorrectionRow, Feedback } from '@/api/corrections'

const auth = useAuthStore()

const tasks = ref<Task[]>([])
const currentTaskId = ref<number | null>(null)
const currentImageUrl = ref<string>('')
const detections = ref<Detection[]>([])
const selectedId = ref<number | null>(null)
const selected = computed(() => detections.value.find((d) => d.id === selectedId.value) ?? null)
const loading = ref(false)
const showFeedback = ref(false)
const feedbackText = ref('')
const auditRows = ref<CorrectionRow[]>([])
const tickets = ref<Feedback[]>([])
const activeTab = ref<'annotate' | 'audit' | 'tickets'>('annotate')

const relabelDialog = ref(false)
const relabelForm = reactive({ newClass: '' })

async function refreshTasks() {
  const page = await listTasks({ pageSize: 50 })
  tasks.value = page.items
  if (currentTaskId.value == null && tasks.value.length > 0) {
    await selectTask(tasks.value[0].id)
  }
}

async function selectTask(taskId: number) {
  currentTaskId.value = taskId
  selectedId.value = null
  loading.value = true
  try {
    detections.value = await getTaskDetections(taskId)
    const first = detections.value[0]
    currentImageUrl.value = first?.result_path
      ? `/api/files/${first.result_path}`
      : first?.image_path
        ? `/api/files/${first.image_path}`
        : ''
    await refreshAudit()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function refreshAudit() {
  if (currentTaskId.value == null) return
  const page = await listAudit({ taskId: currentTaskId.value, pageSize: 50 })
  auditRows.value = page.items
}

async function refreshTickets() {
  const page = await listFeedback({ mine: !auth.isAdmin, pageSize: 50 })
  tickets.value = page.items
}

async function onUpload(file: File) {
  loading.value = true
  try {
    const res = await uploadAndDetect(file, {})
    await refreshTasks()
    await selectTask(res.task_id)
    ElMessage.success(`识别完成，${res.detections.length} 个目标，可开始校正`)
    activeTab.value = 'annotate'
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '识别失败')
  } finally {
    loading.value = false
  }
}

function onSelect(id: number | null) {
  selectedId.value = id
}

async function apply(action: 'confirm' | 'false_positive') {
  if (!selected.value) return
  try {
    await createCorrection({ action, detection_id: selected.value.id })
    await reloadCurrent()
    ElMessage.success(action === 'confirm' ? '已确认' : '已标记误检')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '操作失败')
  }
}

async function openRelabel() {
  if (!selected.value) return
  relabelForm.newClass = selected.value.class_name_zh ?? selected.value.class_name
  relabelDialog.value = true
}

async function submitRelabel() {
  if (!selected.value || !relabelForm.newClass.trim()) return
  try {
    await createCorrection({
      action: 'relabel',
      detection_id: selected.value.id,
      new_class_name: relabelForm.newClass.trim(),
    })
    relabelDialog.value = false
    await reloadCurrent()
    ElMessage.success('已改标签')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '操作失败')
  }
}

async function onAdjust(id: number, bbox: BBox) {
  try {
    await createCorrection({ action: 'adjust', detection_id: id, new_bbox: bbox })
    await reloadCurrent()
    ElMessage.success('框已更新')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '调整失败')
    await reloadCurrent()
  }
}

async function onAdd(bbox: BBox) {
  if (currentTaskId.value == null) return
  try {
    await ElMessageBox.prompt('新框的类别名', '补检', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '类别不能为空',
    }).then(async ({ value }) => {
      await createCorrection({
        action: 'add',
        task_id: currentTaskId.value!,
        new_class_name: value.trim(),
        new_bbox: bbox,
      })
      await reloadCurrent()
      ElMessage.success('已补框')
    })
  } catch {
    /* user cancelled */
  }
}

async function onUndo() {
  try {
    await undo()
    await reloadCurrent()
    ElMessage.success('已撤销最近一次校正')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '撤销失败')
  }
}

async function reloadCurrent() {
  if (currentTaskId.value == null) return
  detections.value = await getTaskDetections(currentTaskId.value)
  await refreshAudit()
}

async function submitFeedback() {
  if (!feedbackText.value.trim()) return
  try {
    await createFeedback({
      content: feedbackText.value.trim(),
      detection_id: selectedId.value ?? undefined,
      task_id: currentTaskId.value ?? undefined,
    })
    feedbackText.value = ''
    showFeedback.value = false
    await refreshTickets()
    ElMessage.success('反馈已提交')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '提交失败')
  }
}

async function onReply(ticket: Feedback) {
  try {
    const { value } = await ElMessageBox.prompt('回复内容', `回复 #${ticket.id}`, {
      confirmButtonText: '发送',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
    })
    await replyFeedback(ticket.id, value.trim())
    await refreshTickets()
    ElMessage.success('已回复')
  } catch {
    /* cancelled */
  }
}

async function onStatusChange(ticket: Feedback, status: string) {
  await updateFeedbackStatus(ticket.id, status)
  await refreshTickets()
}

const statusLabel: Record<string, string> = {
  pending: '待校正',
  corrected: '已校正',
  rejected: '已否决',
}
const statusType: Record<string, 'info' | 'success' | 'danger' | 'warning'> = {
  pending: 'info',
  corrected: 'success',
  rejected: 'danger',
  open: 'warning',
  replied: 'info',
  resolved: 'success',
}

onMounted(async () => {
  await refreshTasks()
  await refreshTickets()
})

watch(currentTaskId, () => {
  if (currentTaskId.value != null) void selectTask(currentTaskId.value)
})
</script>

<template>
  <div class="page annotate">
    <h2>校正工作台</h2>
    <p class="lead">
      这是飞轮的动力源。每一次修正都会写入审计流水，导出时成为模型的训练数据。
    </p>

    <el-tabs v-model="activeTab" class="tabs">
      <el-tab-pane label="标注" name="annotate">
        <div class="toolbar">
          <el-select
            v-if="tasks.length"
            v-model="currentTaskId"
            placeholder="选择任务"
            size="small"
            style="width: 220px"
          >
            <el-option v-for="t in tasks" :key="t.id" :value="t.id" :label="`#${t.id} · ${t.status} · ${t.created_at.slice(0, 16)}`" />
          </el-select>
          <div class="spacer" />
          <el-button size="small" :disabled="!selected" @click="apply('confirm')">✓ 确认</el-button>
          <el-button size="small" :disabled="!selected" @click="openRelabel">改标签</el-button>
          <el-button size="small" :disabled="!selected" type="danger" plain @click="apply('false_positive')">标记误检</el-button>
          <el-button size="small" type="warning" plain @click="onUndo">撤销</el-button>
          <el-button size="small" @click="showFeedback = true">反馈</el-button>
        </div>

        <div class="workbench">
          <section class="canvas-panel">
            <UploadDrop v-if="!currentTaskId" :disabled="loading" @select="onUpload" />
            <template v-else>
              <ImageAnnotator
                :image-src="currentImageUrl"
                :detections="detections"
                :selected-id="selectedId"
                @select="onSelect"
                @adjust="onAdjust"
                @add="onAdd"
              />
              <p class="hint">
                点击选中框 · 拖拽框内移动 · 拖四角调整大小 · 空白处拖拽补框
              </p>
            </template>
          </section>

          <aside class="side-panel">
            <h3>检测明细</h3>
            <DetectionTable :detections="detections" @select="(d) => onSelect(d.id)" />

            <el-descriptions v-if="selected" :column="1" size="small" class="detail" title="选中项">
              <el-descriptions-item label="ID">{{ selected.id }}</el-descriptions-item>
              <el-descriptions-item label="类别">{{ selected.class_name_zh ?? selected.class_name }}</el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag size="small" :type="statusType[selected.status]">{{ statusLabel[selected.status] }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="来源">{{ selected.source === 'model' ? '模型' : '人工' }}</el-descriptions-item>
            </el-descriptions>

            <h3>最近校正</h3>
            <el-timeline v-if="auditRows.length" class="timeline">
              <el-timeline-item
                v-for="row in auditRows.slice(0, 8)"
                :key="row.id"
                :timestamp="`${row.action} · ${row.operator ?? '-'}`"
                placement="top"
              >
                <div class="timeline-body">
                  <div v-if="row.comment" class="comment">"{{ row.comment }}"</div>
                  <code v-if="row.new_value" class="val">{{ row.new_value.slice(0, 80) }}</code>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无校正记录" :image-size="60" />
          </aside>
        </div>
      </el-tab-pane>

      <el-tab-pane :label="`审计流水 (${auditRows.length})`" name="audit">
        <el-table :data="auditRows" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column prop="action" label="动作" width="130">
            <template #default="{ row }">
              <el-tag size="small" :type="row.action === 'undo' ? 'warning' : 'info'">{{ row.action }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detection_id" label="检测" width="80" />
          <el-table-column prop="operator" label="操作人" width="120" />
          <el-table-column prop="comment" label="备注" min-width="180" />
          <el-table-column label="变更" min-width="220">
            <template #default="{ row }">
              <code class="val">{{ row.new_value?.slice(0, 80) ?? '—' }}</code>
            </template>
          </el-table-column>
        </el-table>
        <el-alert type="info" :closable="false" class="note" title="审计流水只追加，永不修改" description="每个动作一条记录。撤销会产生新的 'undo' 条目，原始记录仍保留。" />
      </el-tab-pane>

      <el-tab-pane :label="`反馈工单 (${tickets.length})`" name="tickets">
        <div class="toolbar">
          <el-button size="small" type="primary" @click="showFeedback = true">提交新工单</el-button>
        </div>
        <el-table :data="tickets" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column prop="username" label="提交人" width="110" />
          <el-table-column prop="content" label="内容" min-width="220" />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType[row.status]">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reply" label="回复" min-width="200" />
          <el-table-column v-if="auth.isAdmin" label="操作" width="180">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="onReply(row)">回复</el-button>
              <el-button size="small" text type="success" @click="onStatusChange(row, 'resolved')">解决</el-button>
              <el-button size="small" text type="danger" @click="onStatusChange(row, 'rejected')">驳回</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 改标签对话框 -->
    <el-dialog v-model="relabelDialog" title="修改类别" width="380">
      <el-input v-model="relabelForm.newClass" placeholder="输入新类别（中/英文）" />
      <template #footer>
        <el-button @click="relabelDialog = false">取消</el-button>
        <el-button type="primary" @click="submitRelabel">保存</el-button>
      </template>
    </el-dialog>

    <!-- 反馈对话框 -->
    <el-dialog v-model="showFeedback" title="提交反馈工单" width="420">
      <el-input v-model="feedbackText" type="textarea" :rows="4" placeholder="描述问题（可关联当前选中的检测）" />
      <template #footer>
        <el-button @click="showFeedback = false">取消</el-button>
        <el-button type="primary" @click="submitFeedback">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.lead {
  color: var(--vf-ink-muted);
}
.tabs {
  margin-top: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.spacer {
  flex: 1;
}
.workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}
.canvas-panel .hint {
  margin: 8px 0 0;
  color: var(--vf-ink-muted);
  font-size: 12px;
}
.side-panel {
  background: var(--vf-surface);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg);
  padding: 14px;
}
.side-panel h3 {
  margin: 12px 0 8px;
  font-size: 13px;
}
.detail {
  margin: 8px 0;
}
.timeline {
  max-height: 260px;
  overflow: auto;
}
.timeline-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.comment {
  font-size: 12px;
  color: var(--vf-ink-muted);
}
.val {
  font-family: var(--vf-font-mono);
  font-size: 11px;
  background: var(--vf-bg);
  padding: 2px 4px;
  border-radius: 4px;
}
.note {
  margin-top: 12px;
}
</style>
