<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createUser, listUsers, updateUser } from '@/api/auth'
import { listFeedback, replyFeedback, updateFeedbackStatus } from '@/api/corrections'
import { healthDetail } from '@/api/stats'
import type { HealthDetail } from '@/api/stats'
import type { Feedback } from '@/api/corrections'
import { apiGet, apiPut } from '@/api/http'
import type { User } from '@/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const activeTab = ref<'users' | 'config' | 'audit' | 'feedback' | 'system'>('system')
const loading = ref(false)

// ---- System ----
const health = ref<HealthDetail | null>(null)

// ---- Users ----
const users = ref<User[]>([])
const userDialog = ref(false)
const userForm = reactive({
  id: null as number | null,
  username: '',
  password: '',
  role: 'user' as 'user' | 'admin',
  display_name: '',
  is_active: true,
})

// ---- Config ----
interface ConfigEntry {
  value: unknown
  source: 'db' | 'env' | 'default'
  default: unknown
}
const config = ref<Record<string, ConfigEntry>>({})
const configEdits = ref<Record<string, string>>({})
const configLabels: Record<string, string> = {
  default_conf_threshold: '默认置信度',
  default_iou_threshold: '默认 IoU',
  default_imgsz: '默认推理尺寸',
  default_val_ratio: '验证集比例',
  default_holdout_ratio: '评估集比例',
  enable_fallback_detector: '允许降级检测器',
  default_weight_id: '默认权重 ID',
  label_map: '标签映射',
  llm_model: 'LLM 模型',
  embedding_model: 'Embedding 模型',
}

// ---- Audit ----
interface AuditRow {
  id: number
  entity: string
  entity_key: string
  old_value: string | null
  new_value: string | null
  operator: string | null
  action: string
  created_at: string
}
const audit = ref<AuditRow[]>([])
const auditEntity = ref<string | null>(null)

// ---- Feedback ----
const tickets = ref<Feedback[]>([])

const roleLabel = (r: string) => (r === 'admin' ? '管理员' : '操作员')
const statusType: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
  open: 'warning',
  replied: 'info',
  resolved: 'success',
  rejected: 'danger',
}

async function refresh() {
  loading.value = true
  try {
    const [h, u, c, a, f] = await Promise.all([
      healthDetail(),
      listUsers(),
      apiGet<{ values: Record<string, ConfigEntry> }>('/api/config'),
      apiGet<AuditRow[]>('/api/admin/audit', { limit: 200 }),
      listFeedback({ pageSize: 100 }),
    ])
    health.value = h
    users.value = u
    config.value = c.values ?? {}
    audit.value = a
    tickets.value = f.items
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreateUser() {
  userForm.id = null
  userForm.username = ''
  userForm.password = ''
  userForm.role = 'user'
  userForm.display_name = ''
  userForm.is_active = true
  userDialog.value = true
}

function openEditUser(u: User) {
  userForm.id = u.id
  userForm.username = u.username
  userForm.password = ''
  userForm.role = u.role
  userForm.display_name = u.display_name ?? ''
  userForm.is_active = u.is_active
  userDialog.value = true
}

async function saveUser() {
  try {
    if (userForm.id == null) {
      await createUser({
        username: userForm.username,
        password: userForm.password,
        role: userForm.role,
        display_name: userForm.display_name || undefined,
      })
      ElMessage.success('用户已创建')
    } else {
      await updateUser(userForm.id, {
        role: userForm.role,
        is_active: userForm.is_active,
        display_name: userForm.display_name,
        ...(userForm.password ? { password: userForm.password } : {}),
      })
      ElMessage.success('用户已更新')
    }
    userDialog.value = false
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  }
}

async function toggleUser(u: User) {
  await updateUser(u.id, { is_active: !u.is_active })
  await refresh()
}

async function saveConfig(key: string) {
  const raw = configEdits.value[key]
  if (raw == null) return
  let value: unknown = raw
  if (raw === 'true') value = true
  else if (raw === 'false') value = false
  else if (raw === 'null') value = null
  else if (!Number.isNaN(Number(raw)) && raw.trim() !== '') value = Number(raw)
  try {
    await apiPut(`/api/config/${key}`, { value })
    ElMessage.success(`已更新 ${key}`)
    await refresh()
    delete configEdits.value[key]
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '更新失败')
  }
}

async function replyTicket(t: Feedback) {
  try {
    const { value } = await ElMessageBox.prompt('回复内容', `回复 #${t.id}`, {
      confirmButtonText: '发送',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
    })
    await replyFeedback(t.id, value.trim())
    await refresh()
    ElMessage.success('已回复')
  } catch {
    /* cancelled */
  }
}

async function setStatus(t: Feedback, status: string) {
  await updateFeedbackStatus(t.id, status)
  await refresh()
}

const filteredAudit = computed(() => {
  if (!auditEntity.value) return audit.value
  return audit.value.filter((r) => r.entity === auditEntity.value)
})

onMounted(refresh)
</script>

<template>
  <div class="page admin">
    <h2>系统管理</h2>
    <p class="lead">用户、配置、审计、工单——所有管理操作集中在这一处。</p>

    <el-tabs v-model="activeTab">
      <!-- 系统状态 -->
      <el-tab-pane label="系统状态" name="system">
        <div class="sys-grid">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="应用">{{ health?.app }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ health?.version }}</el-descriptions-item>
            <el-descriptions-item label="数据库">
              <el-tag size="small" :type="health?.db === 'ok' ? 'success' : 'danger'">
                {{ health?.db }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="数据库类型">{{ health?.database_url_scheme }}</el-descriptions-item>
            <el-descriptions-item label="检测器">
              <el-tag size="small" :type="health?.detector_mode === 'yolo' ? 'success' : 'warning'">
                {{ health?.detector_mode }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="降级兜底">
              <el-tag size="small" :type="health?.fallback_enabled ? 'success' : 'info'">
                {{ health?.fallback_enabled ? '启用' : '禁用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="用户数">{{ health?.user_count }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-tab-pane>

      <!-- 用户管理 -->
      <el-tab-pane :label="`用户管理 (${users.length})`" name="users">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="openCreateUser">新建用户</el-button>
        </div>
        <el-table :data="users" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="display_name" label="显示名" width="140" />
          <el-table-column prop="role" label="角色" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.role === 'admin' ? 'warning' : 'info'">
                {{ roleLabel(row.role) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_active ? 'success' : 'danger'">
                {{ row.is_active ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openEditUser(row)">编辑</el-button>
              <el-button
                size="small"
                text
                :type="row.is_active ? 'danger' : 'success'"
                :disabled="row.id === auth.user?.id"
                @click="toggleUser(row)"
              >
                {{ row.is_active ? '禁用' : '启用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 配置 -->
      <el-tab-pane label="系统配置" name="config">
        <el-alert type="info" :closable="false" class="note" title="配置三级优先级" description="数据库 > 环境变量 > 代码默认。此处修改的是数据库层，立即生效（ADR-003）。" />
        <el-table :data="Object.entries(config).map(([k, v]) => ({ key: k, ...v }))" size="small">
          <el-table-column label="键" width="220">
            <template #default="{ row }">
              <div>{{ configLabels[row.key] ?? row.key }}</div>
              <code class="key">{{ row.key }}</code>
            </template>
          </el-table-column>
          <el-table-column label="当前值" min-width="180">
            <template #default="{ row }">
              <el-input
                v-if="configEdits[row.key] !== undefined"
                v-model="configEdits[row.key]"
                size="small"
              />
              <code v-else class="val">{{ JSON.stringify(row.value) }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="source" label="来源" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.source === 'db' ? 'success' : row.source === 'env' ? 'warning' : 'info'">
                {{ row.source }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="默认值" min-width="150">
            <template #default="{ row }">
              <code class="val">{{ JSON.stringify(row.default) }}</code>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <template v-if="configEdits[row.key] !== undefined">
                <el-button size="small" text type="primary" @click="saveConfig(row.key)">保存</el-button>
                <el-button size="small" text @click="delete configEdits[row.key]">取消</el-button>
              </template>
              <el-button v-else size="small" text type="primary" @click="configEdits[row.key] = String(row.value ?? '')">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 审计 -->
      <el-tab-pane :label="`审计日志 (${audit.length})`" name="audit">
        <div class="toolbar">
          <el-select v-model="auditEntity" placeholder="按类型筛选" clearable size="small" style="width: 180px">
            <el-option value="config" label="配置" />
            <el-option value="correction" label="校正" />
            <el-option value="weight" label="权重" />
          </el-select>
          <span class="hint">{{ filteredAudit.length }} 条记录</span>
        </div>
        <el-table :data="filteredAudit" size="small" max-height="500">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column prop="entity" label="类型" width="100" />
          <el-table-column prop="entity_key" label="键" width="180" />
          <el-table-column prop="action" label="动作" width="100" />
          <el-table-column prop="operator" label="操作人" width="120" />
          <el-table-column label="旧值" min-width="180">
            <template #default="{ row }">
              <code class="val">{{ (row.old_value ?? '').slice(0, 60) }}</code>
            </template>
          </el-table-column>
          <el-table-column label="新值" min-width="180">
            <template #default="{ row }">
              <code class="val">{{ (row.new_value ?? '').slice(0, 60) }}</code>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 工单 -->
      <el-tab-pane :label="`反馈工单 (${tickets.length})`" name="feedback">
        <el-table :data="tickets" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column prop="username" label="提交人" width="120" />
          <el-table-column prop="content" label="内容" min-width="220" />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType[row.status]">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reply" label="回复" min-width="180" />
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="replyTicket(row)">回复</el-button>
              <el-button size="small" text type="success" @click="setStatus(row, 'resolved')">解决</el-button>
              <el-button size="small" text type="danger" @click="setStatus(row, 'rejected')">驳回</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 用户对话框 -->
    <el-dialog v-model="userDialog" :title="userForm.id ? '编辑用户' : '新建用户'" width="420">
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="userForm.username" :disabled="userForm.id != null" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="userForm.password" type="password" :placeholder="userForm.id ? '留空则不修改' : ''" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="userForm.display_name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="userForm.role">
            <el-radio value="user">操作员</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="userForm.id" label="状态">
          <el-switch v-model="userForm.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button type="primary" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.lead {
  color: var(--vf-ink-muted);
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
.note {
  margin-bottom: 12px;
}
.key {
  font-family: var(--vf-font-mono);
  font-size: 11px;
  color: var(--vf-ink-muted);
}
.val {
  font-family: var(--vf-font-mono);
  font-size: 11px;
  background: var(--vf-bg);
  padding: 2px 4px;
  border-radius: 4px;
}
.sys-grid {
  max-width: 820px;
}
</style>
