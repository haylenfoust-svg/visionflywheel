<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createFeedback, createCorrection, listAudit, listFeedback, replyFeedback, undo, updateFeedbackStatus } from '@/api/corrections'
import { getTaskDetections, listTasks, uploadAndDetect } from '@/api/tasks'
import AppCard from '@/components/AppCard.vue'
import DetectionTable from '@/components/DetectionTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import ImageAnnotator from '@/components/ImageAnnotator.vue'
import PageHeader from '@/components/PageHeader.vue'
import UploadDrop from '@/components/UploadDrop.vue'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'
import type { BBox, Detection, Task } from '@/types/detection'
import type { CorrectionRow, Feedback } from '@/api/corrections'

const auth = useAuthStore()
const { can } = usePermissions()

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
const undoLoading = ref(false)

const relabelDialog = ref(false)
const relabelForm = reactive({ newClass: '' })

const statusLabel: Record<string, string> = {
  pending: '待校正',
  corrected: '已校正',
  rejected: '已否决',
}
const statusType: Record<string, 'chip-success' | 'chip-warning' | 'chip-danger' | 'chip-neutral' | 'chip-primary'> = {
  pending: 'chip-warning',
  corrected: 'chip-success',
  rejected: 'chip-danger',
  open: 'chip-warning',
  replied: 'chip-primary',
  resolved: 'chip-success',
}
const actionLabel: Record<string, string> = {
  confirm: '确认',
  relabel: '改标签',
  false_positive: '标误检',
  adjust: '改框',
  add: '补框',
  undo: '撤销',
}

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
    ElMessage.success(action === 'confirm' ? '✓ 已确认' : '⚠ 已标记误检')
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
    ElMessage.success('✎ 标签已修改')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '操作失败')
  }
}

async function onAdjust(id: number, bbox: BBox) {
  try {
    await createCorrection({ action: 'adjust', detection_id: id, new_bbox: bbox })
    await reloadCurrent()
    ElMessage.success('⌗ 框已更新')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '调整失败')
    await reloadCurrent()
  }
}

async function onAdd(bbox: BBox) {
  if (currentTaskId.value == null) return
  try {
    await ElMessageBox.prompt('新框的类别名', '✛ 补检', {
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
      ElMessage.success('✛ 已补框')
    })
  } catch {
    /* user cancelled */
  }
}

async function onUndo() {
  if (undoLoading.value) return
  undoLoading.value = true
  try {
    await undo()
    await reloadCurrent()
    ElMessage.success('↩ 已撤销最近一次校正')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '撤销失败')
  } finally {
    undoLoading.value = false
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
    ElMessage.success('⚑ 反馈已提交')
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

const statCards = computed(() => {
  const counts = detections.value.reduce<Record<string, number>>((acc, d) => {
    acc[d.status] = (acc[d.status] ?? 0) + 1
    return acc
  }, {})
  return [
    { label: '待校正', value: counts['pending'] ?? 0, accent: 'warning' as const },
    { label: '已校正', value: counts['corrected'] ?? 0, accent: 'success' as const },
    { label: '已否决', value: counts['rejected'] ?? 0, accent: 'danger' as const },
  ]
})

onMounted(async () => {
  await refreshTasks()
  await refreshTickets()
})

watch(currentTaskId, () => {
  if (currentTaskId.value != null) void selectTask(currentTaskId.value)
})
</script>

<template>
  <div class="page">
    <PageHeader
      title="校正工作台"
      subtitle="飞轮的动力源。每一次修正都会写入审计流水，导出时成为模型的训练数据。"
      :breadcrumb="[{ text: '控制台', to: '/dashboard' }, { text: '校正工作台' }]"
    >
      <template #actions>
        <el-button
v-if="can('detection.correct')" type="warning" plain size="large" :loading="undoLoading"
          :disabled="!detections.length"
          @click="onUndo"
        >
          ↩ 撤销最近一次
        </el-button>
        <el-button size="large" @click="showFeedback = true">⚑ 反馈问题</el-button>
      </template>
    </PageHeader>

    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-select
        v-if="tasks.length"
        v-model="currentTaskId"
        placeholder="选择任务"
        size="large"
        class="task-select"
      >
        <el-option
          v-for="t in tasks"
          :key="t.id"
          :value="t.id"
          :label="`#${t.id} · ${t.status} · ${t.created_at?.slice(0, 16)}`"
        />
      </el-select>

      <div class="toolbar__spacer" />

      <!-- 快捷校正 -->
      <div class="toolbar__actions">
        <el-button
          type="success"
          :disabled="!selected"
          size="large"
          @click="apply('confirm')"
        >
          ✓ 确认正确
        </el-button>
        <el-button
          type="primary"
          plain
          :disabled="!selected"
          size="large"
          @click="openRelabel"
        >
          ✎ 改标签
        </el-button>
        <el-button
          type="danger"
          plain
          :disabled="!selected"
          size="large"
          @click="apply('false_positive')"
        >
          ⎋ 标误检
        </el-button>
      </div>
    </div>

    <!-- 统计条 -->
    <div v-if="detections.length" class="stat-strip">
      <div v-for="s in statCards" :key="s.label" class="stat-strip__item" :class="`accent-${s.accent}`">
        <span class="stat-strip__label">{{ s.label }}</span>
        <span class="stat-strip__value num">{{ s.value }}</span>
      </div>
    </div>

    <!-- 工作区 -->
    <el-tabs v-model="activeTab" class="tabs">
      <el-tab-pane label="标注" name="annotate">
        <div class="workbench">
          <!-- Canvas -->
          <section class="canvas-panel">
            <UploadDrop v-if="!currentTaskId" :disabled="loading" @select="onUpload" />
            <template v-else>
              <div class="canvas-frame">
                <ImageAnnotator
                  :image-src="currentImageUrl"
                  :detections="detections"
                  :selected-id="selectedId"
                  @select="onSelect"
                  @adjust="onAdjust"
                  @add="onAdd"
                />
              </div>
              <div class="canvas-hints">
                <span class="hint"><kbd>点击</kbd> 选中框</span>
                <span class="hint"><kbd>拖框内</kbd> 移动</span>
                <span class="hint"><kbd>拖四角</kbd> 调整大小</span>
                <span class="hint"><kbd>空白拖拽</kbd> 补框</span>
              </div>
            </template>
          </section>

          <!-- 侧栏 -->
          <aside class="side-panel">
            <AppCard title="检测明细" subtitle="点击行选中">
              <DetectionTable :detections="detections" @select="(d) => onSelect(d.id)" />
            </AppCard>

            <AppCard v-if="selected" title="选中项">
              <div class="detail-grid">
                <div class="detail-item">
                  <div class="detail-item__label">ID</div>
                  <div class="detail-item__value num">{{ selected.id }}</div>
                </div>
                <div class="detail-item">
                  <div class="detail-item__label">类别</div>
                  <div class="detail-item__value">
                    <span class="chip chip-primary">{{ selected.class_name_zh ?? selected.class_name }}</span>
                  </div>
                </div>
                <div class="detail-item">
                  <div class="detail-item__label">状态</div>
                  <div class="detail-item__value">
                    <span class="chip" :class="statusType[selected.status]">
                      {{ statusLabel[selected.status] }}
                    </span>
                  </div>
                </div>
                <div class="detail-item">
                  <div class="detail-item__label">来源</div>
                  <div class="detail-item__value">{{ selected.source === 'model' ? '模型' : '人工' }}</div>
                </div>
              </div>
            </AppCard>

            <AppCard title="最近校正" subtitle="审计流水预览">
              <div v-if="auditRows.length" class="timeline">
                <div v-for="row in auditRows.slice(0, 8)" :key="row.id" class="timeline-item">
                  <div class="timeline-item__dot" :class="row.action === 'undo' ? 'dot-warning' : 'dot-primary'" />
                  <div class="timeline-item__body">
                    <div class="timeline-item__head">
                      <span class="chip" :class="row.action === 'undo' ? 'chip-warning' : 'chip-primary'">
                        {{ actionLabel[row.action] ?? row.action }}
                      </span>
                      <span class="timeline-item__meta">{{ row.operator ?? '-' }}</span>
                    </div>
                    <div v-if="row.comment" class="timeline-item__comment">"{{ row.comment }}"</div>
                  </div>
                </div>
              </div>
              <EmptyState
                v-else
                title="暂无校正记录"
                description="在校正工作台上操作后会显示在这里"
                icon="✎"
                size="sm"
              />
            </AppCard>
          </aside>
        </div>
      </el-tab-pane>

      <el-tab-pane :label="`审计流水 (${auditRows.length})`" name="audit">
        <AppCard>
          <el-table :data="auditRows" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column label="动作" width="130">
              <template #default="{ row }">
                <span class="chip" :class="row.action === 'undo' ? 'chip-warning' : 'chip-primary'">
                  {{ actionLabel[row.action] ?? row.action }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="detection_id" label="检测" width="90" align="right" />
            <el-table-column prop="operator" label="操作人" width="130" />
            <el-table-column prop="comment" label="备注" min-width="180" />
            <el-table-column label="变更" min-width="200">
              <template #default="{ row }">
                <code class="mono">{{ row.new_value?.slice(0, 60) ?? '—' }}</code>
              </template>
            </el-table-column>
          </el-table>
          <el-alert type="info" :closable="false" class="mt-4" show-icon>
            <template #title>审计流水只追加，永不修改</template>
            <template #default>每个动作一条记录。撤销会产生新的 'undo' 条目，原始记录仍保留（PRD FR-3.7）。</template>
          </el-alert>
        </AppCard>
      </el-tab-pane>

      <el-tab-pane :label="`反馈工单 (${tickets.length})`" name="tickets">
        <AppCard>
          <template #actions>
            <el-button type="primary" @click="showFeedback = true">提交新工单</el-button>
          </template>
          <el-table :data="tickets" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column prop="username" label="提交人" width="120" />
            <el-table-column prop="content" label="内容" min-width="220" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <span class="chip" :class="statusType[row.status]">{{ row.status }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="reply" label="回复" min-width="200" />
            <el-table-column v-if="auth.isAdmin" label="操作" width="220">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="onReply(row)">回复</el-button>
                <el-button size="small" text type="success" @click="onStatusChange(row, 'resolved')">解决</el-button>
                <el-button size="small" text type="danger" @click="onStatusChange(row, 'rejected')">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-if="!tickets.length"
            title="暂无工单"
            description="发现问题？提交工单给管理员"
            icon="⚑"
            size="sm"
            action-text="提交"
            @action="showFeedback = true"
          />
        </AppCard>
      </el-tab-pane>
    </el-tabs>

    <!-- 改标签对话框 -->
    <el-dialog v-model="relabelDialog" title="✎ 修改类别" width="420" append-to-body>
      <div class="dialog-form">
        <label class="dialog-label">新类别名</label>
        <el-input v-model="relabelForm.newClass" placeholder="输入中文或英文类别" size="large" />
        <p class="dialog-hint">修改后会写入审计流水，可随时撤销。</p>
      </div>
      <template #footer>
        <el-button @click="relabelDialog = false">取消</el-button>
        <el-button type="primary" @click="submitRelabel">保存</el-button>
      </template>
    </el-dialog>

    <!-- 反馈对话框 -->
    <el-dialog v-model="showFeedback" title="⚑ 提交反馈工单" width="480" append-to-body>
      <div class="dialog-form">
        <label class="dialog-label">问题描述</label>
        <el-input
          v-model="feedbackText"
          type="textarea"
          :rows="5"
          placeholder="描述你发现的问题。可以关联当前选中的检测。"
        />
      </div>
      <template #footer>
        <el-button @click="showFeedback = false">取消</el-button>
        <el-button type="primary" @click="submitFeedback">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mt-4 { margin-top: var(--sp-4); }

.toolbar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
  flex-wrap: wrap;
}
.task-select {
  min-width: 240px;
}
.toolbar__spacer {
  flex: 1;
}
.toolbar__actions {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

/* 统计条 */
.stat-strip {
  display: flex;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}
.stat-strip__item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  border-left-width: 3px;
}
.stat-strip__item.accent-warning { border-left-color: var(--c-warning-500); }
.stat-strip__item.accent-success { border-left-color: var(--c-success-500); }
.stat-strip__item.accent-danger  { border-left-color: var(--c-danger-500); }
.stat-strip__label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.stat-strip__value {
  font-size: var(--fs-2xl);
  font-weight: var(--fw-semibold);
}

/* 工作区 */
.tabs {
  margin-top: var(--sp-2);
}
.workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: var(--sp-3);
  align-items: start;
}

.canvas-frame {
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  overflow: hidden;
}
.canvas-hints {
  display: flex;
  gap: var(--sp-4);
  margin-top: var(--sp-3);
  flex-wrap: wrap;
}
.hint {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}
kbd {
  padding: 2px var(--sp-2);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-bottom-width: 2px;
  border-radius: var(--r-xs);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

/* 详情 */
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
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

/* 时间线 */
.timeline {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.timeline-item {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-start;
}
.timeline-item__dot {
  width: 8px; height: 8px;
  border-radius: var(--r-full);
  margin-top: 6px;
  flex-shrink: 0;
}
.dot-primary { background: var(--c-primary-500); }
.dot-warning { background: var(--c-warning-500); }
.timeline-item__body {
  flex: 1;
  min-width: 0;
}
.timeline-item__head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.timeline-item__meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.timeline-item__comment {
  margin-top: 2px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  font-style: italic;
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

/* 对话框 */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.dialog-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
  color: var(--text-secondary);
}
.dialog-hint {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

@media (max-width: 1000px) {
  .workbench { grid-template-columns: 1fr; }
}
</style>
