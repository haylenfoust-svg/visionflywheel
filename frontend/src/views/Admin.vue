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
import AppCard from '@/components/AppCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'

const auth = useAuthStore()
const { can } = usePermissions()
const activeTab = ref<'system' | 'users' | 'config' | 'audit' | 'feedback'>('system')
const loading = ref(false)

const health = ref<HealthDetail | null>(null)
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
const sourceChip: Record<string, string> = {
  db: 'chip-success',
  env: 'chip-warning',
  default: 'chip-neutral',
}

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

const tickets = ref<Feedback[]>([])

const filteredAudit = computed(() => {
  if (!auditEntity.value) return audit.value
  return audit.value.filter((r) => r.entity === auditEntity.value)
})

const statusChip: Record<string, string> = {
  open: 'chip-warning',
  replied: 'chip-primary',
  resolved: 'chip-success',
  rejected: 'chip-danger',
  user: 'chip-neutral',
  admin: 'chip-warning',
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
      ElMessage.success('✓ 用户已创建')
    } else {
      await updateUser(userForm.id, {
        role: userForm.role,
        is_active: userForm.is_active,
        display_name: userForm.display_name,
        ...(userForm.password ? { password: userForm.password } : {}),
      })
      ElMessage.success('✓ 用户已更新')
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
    ElMessage.success(`✓ 已更新 ${key}`)
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

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader
      title="系统管理"
      subtitle="用户、配置、审计、工单——所有管理操作集中在这一处。"
      :breadcrumb="[{ text: '控制台', to: '/dashboard' }, { text: '系统管理' }]"
    />

    <!-- 顶部统计 -->
    <div class="stats-grid">
      <StatCard label="用户" :value="users.length" accent="neutral" icon="👥" />
      <StatCard label="配置项" :value="Object.keys(config).length" accent="neutral" icon="⚙" />
      <StatCard label="审计条目" :value="audit.length" accent="primary" icon="📋" />
      <StatCard label="工单" :value="tickets.length" accent="warning" icon="⚑" />
    </div>

    <el-tabs v-model="activeTab">
      <!-- 系统状态 -->
      <el-tab-pane label="系统状态" name="system">
        <AppCard title="运行时信息" subtitle="系统健康与引擎状态">
          <div v-if="health" class="system-grid">
            <div class="system-item">
              <div class="system-item__label">应用</div>
              <div class="system-item__value">{{ health.app }}</div>
            </div>
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
              <div class="system-item__label">数据库类型</div>
              <div class="system-item__value mono">{{ health.database_url_scheme }}</div>
            </div>
            <div class="system-item">
              <div class="system-item__label">检测器</div>
              <div class="system-item__value">
                <span class="chip" :class="health.detector_mode === 'yolo' ? 'chip-success' : 'chip-warning'">
                  {{ health.detector_mode }}
                </span>
              </div>
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
              <div class="system-item__label">用户数</div>
              <div class="system-item__value num">{{ health.user_count }}</div>
            </div>
          </div>
        </AppCard>
      </el-tab-pane>

      <!-- 用户管理 -->
      <el-tab-pane :label="`用户 (${users.length})`" name="users">
        <AppCard>
          <template #actions>
            <el-button v-if="can('user.write')" type="primary" @click="openCreateUser">+ 新建用户</el-button>
          </template>
          <el-table :data="users" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="username" label="用户名" min-width="140" />
            <el-table-column prop="display_name" label="显示名" min-width="140" />
            <el-table-column label="角色" width="110">
              <template #default="{ row }">
                <span class="chip" :class="statusChip[row.role]">
                  {{ row.role === 'admin' ? '管理员' : '操作员' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span class="chip" :class="row.is_active ? 'chip-success' : 'chip-danger'">
                  {{ row.is_active ? '启用' : '禁用' }}
                </span>
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
        </AppCard>
      </el-tab-pane>

      <!-- 配置 -->
      <el-tab-pane label="系统配置" name="config">
        <AppCard title="配置三级优先级" subtitle="数据库 > 环境变量 > 代码默认（ADR-003）">
          <el-table :data="Object.entries(config).map(([k, v]) => ({ key: k, ...v }))" size="default">
            <el-table-column label="键" min-width="220">
              <template #default="{ row }">
                <div class="config-key">
                  <div class="config-key__name">{{ configLabels[row.key] ?? row.key }}</div>
                  <code class="mono config-key__id">{{ row.key }}</code>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="当前值" min-width="200">
              <template #default="{ row }">
                <el-input
                  v-if="configEdits[row.key] !== undefined"
                  v-model="configEdits[row.key]"
                  size="small"
                />
                <code v-else class="mono">{{ JSON.stringify(row.value) }}</code>
              </template>
            </el-table-column>
            <el-table-column label="来源" width="110">
              <template #default="{ row }">
                <span class="chip" :class="sourceChip[row.source]">{{ row.source }}</span>
              </template>
            </el-table-column>
            <el-table-column label="默认值" min-width="150">
              <template #default="{ row }">
                <code class="mono text-subtle">{{ JSON.stringify(row.default) }}</code>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="170">
              <template #default="{ row }">
                <template v-if="configEdits[row.key] !== undefined">
                  <el-button size="small" text type="primary" @click="saveConfig(row.key)">保存</el-button>
                  <el-button size="small" text @click="delete configEdits[row.key]">取消</el-button>
                </template>
                <el-button
                  v-else
                  size="small"
                  text
                  type="primary"
                  @click="configEdits[row.key] = String(row.value ?? '')"
                >
                  编辑
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </AppCard>
      </el-tab-pane>

      <!-- 审计 -->
      <el-tab-pane :label="`审计 (${audit.length})`" name="audit">
        <AppCard>
          <template #actions>
            <el-select v-model="auditEntity" placeholder="按类型筛选" clearable style="width: 180px">
              <el-option value="config" label="配置" />
              <el-option value="correction" label="校正" />
              <el-option value="weight" label="权重" />
            </el-select>
            <span class="text-subtle ml-2">{{ filteredAudit.length }} 条记录</span>
          </template>
          <el-table :data="filteredAudit" size="default" max-height="500">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column label="类型" width="110">
              <template #default="{ row }">
                <span class="chip chip-neutral">{{ row.entity }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="entity_key" label="键" min-width="150" />
            <el-table-column label="动作" width="110">
              <template #default="{ row }">
                <span class="chip" :class="row.action === 'delete' ? 'chip-danger' : 'chip-primary'">
                  {{ row.action }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="operator" label="操作人" width="120" />
            <el-table-column label="旧值 → 新值" min-width="220">
              <template #default="{ row }">
                <div class="audit-change">
                  <code class="mono">{{ (row.old_value ?? '—').slice(0, 30) }}</code>
                  <span class="audit-arrow">→</span>
                  <code class="mono">{{ (row.new_value ?? '—').slice(0, 30) }}</code>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-if="!filteredAudit.length"
            title="暂无审计记录"
            description="配置变更和用户操作会记录在这里"
            icon="📋"
            size="sm"
          />
        </AppCard>
      </el-tab-pane>

      <!-- 工单 -->
      <el-tab-pane :label="`工单 (${tickets.length})`" name="feedback">
        <AppCard>
          <el-table :data="tickets" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column prop="username" label="提交人" width="120" />
            <el-table-column prop="content" label="内容" min-width="220" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <span class="chip" :class="statusChip[row.status]">{{ row.status }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="reply" label="回复" min-width="200" />
            <el-table-column label="操作" width="220">
              <template #default="{ row }">
                <el-button v-if="can('feedback.manage')" size="small" text type="primary" @click="replyTicket(row)">回复</el-button>
                <el-button v-if="can('feedback.manage')" size="small" text type="success" @click="setStatus(row, 'resolved')">解决</el-button>
                <el-button v-if="can('feedback.manage')" size="small" text type="danger" @click="setStatus(row, 'rejected')">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-if="!tickets.length"
            title="暂无工单"
            description="用户提交的反馈会显示在这里"
            icon="⚑"
            size="sm"
          />
        </AppCard>
      </el-tab-pane>
    </el-tabs>

    <!-- 用户对话框 -->
    <el-dialog v-model="userDialog" :title="userForm.id ? '✎ 编辑用户' : '+ 新建用户'" width="460" append-to-body>
      <div class="dialog-form">
        <div class="field">
          <label class="field-label">用户名</label>
          <el-input v-model="userForm.username" :disabled="userForm.id != null" size="large" />
        </div>
        <div class="field">
          <label class="field-label">密码</label>
          <el-input
            v-model="userForm.password"
            type="password"
            size="large"
            :placeholder="userForm.id ? '留空则不修改' : ''"
          />
        </div>
        <div class="field">
          <label class="field-label">显示名</label>
          <el-input v-model="userForm.display_name" size="large" />
        </div>
        <div class="field">
          <label class="field-label">角色</label>
          <el-radio-group v-model="userForm.role">
            <el-radio value="user">操作员</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </div>
        <div v-if="userForm.id" class="field">
          <label class="field-label">状态</label>
          <el-switch v-model="userForm.is_active" active-text="启用" inactive-text="禁用" />
        </div>
      </div>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button v-if="can('user.write')" type="primary" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ml-2 { margin-left: var(--sp-2); }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-6);
}

.system-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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

.config-key__name {
  font-size: var(--fs-md);
  font-weight: var(--fw-medium);
}
.config-key__id {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.audit-change {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-xs);
}
.audit-arrow {
  color: var(--text-tertiary);
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

/* 对话框 */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
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
</style>
