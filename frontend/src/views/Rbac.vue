<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  addTeamMember,
  assignRole,
  createOrg,
  createRole,
  createTeam,
  deleteOrg,
  deleteRole,
  getUserRoles,
  listAllSessions,
  listLoginAttempts,
  listMySessions,
  listOrgs,
  listPermissions,
  listRoles,
  listTeams,
  removeTeamMember,
  revokeSession,
  teamMembers,
  unassignRole,
  updateOrg,
  updateRole,
} from '@/api/rbac'
import type {
  LoginAttempt,
  Organization,
  PermissionCatalog,
  Role,
  Session,
  Team,
  TeamMember,
  UserRoleBinding,
} from '@/api/rbac'
import { createUser, listUsers, updateUser } from '@/api/auth'
import { usePermissions } from '@/composables/usePermissions'
import { usePermissionStore } from '@/stores/permission'
import type { User } from '@/types'
import AppCard from '@/components/AppCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'
import type { Column } from '@/components/DataTable.vue'

const { can } = usePermissions()
const permStore = usePermissionStore()
const activeTab = ref<'users' | 'roles' | 'orgs' | 'teams' | 'sessions' | 'audit'>('users')
const loading = ref(false)

// ---------- users ----------
const users = ref<User[]>([])
const userRoles = ref<Record<number, UserRoleBinding[]>>({})
const userDialog = ref(false)
const userForm = reactive({
  id: null as number | null,
  username: '',
  password: '',
  role: 'user' as 'user' | 'admin',
  display_name: '',
  is_active: true,
})

const userColumns: Column[] = [
  { key: 'id', label: '#', width: 70, sortable: true },
  { key: 'username', label: '用户名', sortable: true },
  { key: 'display_name', label: '显示名' },
  { key: 'role', label: '内置角色', width: 110, slot: 'role' },
  { key: 'roles', label: 'RBAC 角色', slot: 'roles', width: 220 },
  { key: 'is_active', label: '状态', width: 100, slot: 'status' },
  { key: 'created_at', label: '创建时间', width: 180, sortable: true },
]

// ---------- roles ----------
const roles = ref<Role[]>([])
const catalog = ref<PermissionCatalog | null>(null)
const roleDialog = ref(false)
const roleForm = reactive({
  id: null as number | null,
  code: '',
  name: '',
  description: '',
  permission_codes: [] as string[],
})
const matrixOpen = ref<number | null>(null)

// ---------- orgs ----------
const orgs = ref<Organization[]>([])
const orgDialog = ref(false)
const orgForm = reactive({
  id: null as number | null,
  name: '',
  code: '',
  parent_id: null as number | null,
  description: '',
})

// ---------- teams ----------
const teams = ref<Team[]>([])
const teamDialog = ref(false)
const teamForm = reactive({
  id: null as number | null,
  name: '',
  code: '',
  org_id: null as number | null,
  description: '',
})
const teamMembersMap = ref<Record<number, TeamMember[]>>({})

// ---------- sessions ----------
const mySessions = ref<Session[]>([])
const allSessions = ref<Session[]>([])

// ---------- audit ----------
const attempts = ref<LoginAttempt[]>([])

async function refresh() {
  loading.value = true
  try {
    const [u, r, o, t, myS, allS, att] = await Promise.all([
      listUsers(),
      listRoles(),
      listOrgs(),
      listTeams(),
      listMySessions(),
      listAllSessions().catch(() => []),
      listLoginAttempts(100).catch(() => []),
    ])
    users.value = u
    roles.value = r
    orgs.value = o
    teams.value = t
    catalog.value = await listPermissions().catch(() => null)
    mySessions.value = myS
    allSessions.value = allS
    attempts.value = att

    // Fetch RBAC role bindings for each user
    for (const user of u) {
      try {
        userRoles.value[user.id] = await getUserRoles(user.id)
      } catch {
        userRoles.value[user.id] = []
      }
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

// ---------- users ----------
function openCreateUser() {
  userForm.id = null
  userForm.username = ''
  userForm.password = ''
  userForm.role = 'user'
  userForm.display_name = ''
  userForm.is_active = true
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

async function onBindRole(u: User) {
  const options = roles.value.map((r) => ({ value: r.code, label: `${r.name} (${r.code})` }))
  try {
    const { value } = await ElMessageBox.prompt(
      `为 ${u.username} 分配角色（输入 code）：\n可选：${options.map((o) => o.value).join(' / ')}`,
      '分配 RBAC 角色',
      { inputPattern: /\S+/, confirmButtonText: '分配', cancelButtonText: '取消' },
    )
    await assignRole(u.id, { role_code: value.trim(), scope_type: 'global', scope_id: null })
    ElMessage.success('✓ 角色已分配')
    await refresh()
    await permStore.refresh()
  } catch {
    /* cancelled */
  }
}

async function onUnbindRole(u: User, binding: UserRoleBinding) {
  try {
    await ElMessageBox.confirm(
      `撤销 ${u.username} 的 ${binding.role_name} 角色？`,
      '确认',
      { type: 'warning' },
    )
    await unassignRole(u.id, binding.role_id)
    await refresh()
    ElMessage.success('✓ 已撤销')
  } catch {
    /* cancelled */
  }
}

// ---------- roles ----------
function openCreateRole() {
  roleForm.id = null
  roleForm.code = ''
  roleForm.name = ''
  roleForm.description = ''
  roleForm.permission_codes = []
  roleDialog.value = true
}

function openEditRole(r: Role) {
  roleForm.id = r.id
  roleForm.code = r.code
  roleForm.name = r.name
  roleForm.description = r.description ?? ''
  roleForm.permission_codes = [...r.permissions]
  roleDialog.value = true
}

async function saveRole() {
  try {
    if (roleForm.id == null) {
      await createRole({
        code: roleForm.code,
        name: roleForm.name,
        description: roleForm.description,
        permission_codes: roleForm.permission_codes,
      })
      ElMessage.success('✓ 角色已创建')
    } else {
      await updateRole(roleForm.id, {
        name: roleForm.name,
        description: roleForm.description,
        permission_codes: roleForm.permission_codes,
      })
      ElMessage.success('✓ 角色已更新')
    }
    roleDialog.value = false
    await refresh()
    // Permissions may have changed — refresh the current user's set
    await permStore.refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  }
}

async function onDeleteRole(r: Role) {
  if (r.is_system) {
    ElMessage.warning('系统角色不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(`删除角色 ${r.name}？`, '确认', { type: 'warning' })
    await deleteRole(r.id)
    ElMessage.success('✓ 已删除')
    await refresh()
  } catch {
    /* cancelled */
  }
}

function togglePermissionInRole(code: string) {
  const idx = roleForm.permission_codes.indexOf(code)
  if (idx >= 0) roleForm.permission_codes.splice(idx, 1)
  else roleForm.permission_codes.push(code)
}

function toggleAllInCategory(category: string) {
  const perms = catalog.value?.permissions[category] ?? []
  const allSelected = perms.every((p) => roleForm.permission_codes.includes(p.code))
  if (allSelected) {
    // remove all
    roleForm.permission_codes = roleForm.permission_codes.filter(
      (code) => !perms.some((p) => p.code === code),
    )
  } else {
    // add missing
    for (const p of perms) {
      if (!roleForm.permission_codes.includes(p.code)) roleForm.permission_codes.push(p.code)
    }
  }
}

function isCategoryAllSelected(category: string): boolean {
  const perms = catalog.value?.permissions[category] ?? []
  return perms.length > 0 && perms.every((p) => roleForm.permission_codes.includes(p.code))
}

// ---------- orgs ----------
function openCreateOrg() {
  orgForm.id = null
  orgForm.name = ''
  orgForm.code = ''
  orgForm.parent_id = null
  orgForm.description = ''
  orgDialog.value = true
}

async function saveOrg() {
  try {
    if (orgForm.id == null) {
      await createOrg({
        name: orgForm.name,
        code: orgForm.code,
        parent_id: orgForm.parent_id,
        description: orgForm.description,
      })
      ElMessage.success('✓ 组织已创建')
    } else {
      await updateOrg(orgForm.id, {
        name: orgForm.name,
        description: orgForm.description,
        parent_id: orgForm.parent_id,
      })
      ElMessage.success('✓ 组织已更新')
    }
    orgDialog.value = false
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  }
}

async function onDeleteOrg(o: Organization) {
  try {
    await ElMessageBox.confirm(`删除组织 ${o.name}？`, '确认', { type: 'warning' })
    await deleteOrg(o.id)
    ElMessage.success('✓ 已删除')
    await refresh()
  } catch {
    /* cancelled */
  }
}

// ---------- teams ----------
function openCreateTeam() {
  teamForm.id = null
  teamForm.name = ''
  teamForm.code = ''
  teamForm.org_id = null
  teamForm.description = ''
  teamDialog.value = true
}

async function saveTeam() {
  try {
    await createTeam({
      name: teamForm.name,
      code: teamForm.code,
      org_id: teamForm.org_id,
      description: teamForm.description,
    })
    ElMessage.success('✓ 团队已创建')
    teamDialog.value = false
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  }
}

async function viewTeamMembers(t: Team) {
  teamMembersMap.value[t.id] = await teamMembers(t.id)
}

async function onAddTeamMember(t: Team) {
  try {
    const { value } = await ElMessageBox.prompt(
      '输入用户 ID',
      `添加成员到 ${t.name}`,
      { inputPattern: /^\d+$/, inputErrorMessage: '请输入数字 ID' },
    )
    await addTeamMember(t.id, { user_id: Number(value), role: 'member' })
    ElMessage.success('✓ 已添加')
    await viewTeamMembers(t)
    await refresh()
  } catch {
    /* cancelled */
  }
}

async function onRemoveTeamMember(t: Team, m: TeamMember) {
  try {
    await ElMessageBox.confirm(`将 ${m.username} 移出 ${t.name}？`, '确认', { type: 'warning' })
    await removeTeamMember(t.id, m.user_id)
    await viewTeamMembers(t)
    await refresh()
    ElMessage.success('✓ 已移出')
  } catch {
    /* cancelled */
  }
}

// ---------- sessions ----------
async function onRevoke(s: Session) {
  try {
    await ElMessageBox.confirm(`强制下线该会话？（${s.ip_address ?? '未知 IP'}）`, '确认', { type: 'warning' })
    await revokeSession(s.session_id)
    await refresh()
    ElMessage.success('✓ 已下线')
  } catch {
    /* cancelled */
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader
      title="身份与权限"
      subtitle="RBAC 角色矩阵 · 组织团队 · 会话管理 · 登录审计"
      :breadcrumb="[{ text: '控制台', to: '/dashboard' }, { text: '身份与权限' }]"
    >
      <template #actions>
        <el-button size="large" @click="refresh">↻ 刷新</el-button>
      </template>
    </PageHeader>

    <!-- 统计 -->
    <div class="stats-grid">
      <StatCard label="用户" :value="users.length" accent="primary" icon="👥" />
      <StatCard label="角色" :value="roles.length" accent="neutral" icon="🛡" />
      <StatCard label="权限码" :value="Object.values(catalog?.permissions ?? {}).flat().length" accent="neutral" icon="🔑" />
      <StatCard label="组织 / 团队" :value="`${orgs.length} / ${teams.length}`" accent="neutral" icon="🏢" />
      <StatCard label="活跃会话" :value="allSessions.filter((s) => s.is_active).length" accent="success" icon="🖥" />
      <StatCard label="登录审计" :value="attempts.length" accent="warning" icon="📋" />
    </div>

    <el-tabs v-model="activeTab">
      <!-- 用户 -->
      <el-tab-pane :label="`用户 (${users.length})`" name="users">
        <AppCard>
          <template #actions>
            <el-button v-if="can('user.write')" type="primary" @click="openCreateUser">+ 新建用户</el-button>
          </template>
          <DataTable
            :rows="users"
            :columns="userColumns"
            :loading="loading"
            empty-title="暂无用户"
            empty-description="点「新建用户」创建第一个"
            empty-icon="👥"
          >
            <template #role="{ row }">
              <span class="chip" :class="row.role === 'admin' ? 'chip-warning' : 'chip-neutral'">
                {{ row.role === 'admin' ? '管理员' : '操作员' }}
              </span>
            </template>
            <template #roles="{ row }">
              <div class="role-list">
                <span
                  v-for="b in userRoles[row.id] ?? []"
                  :key="b.role_id"
                  class="chip chip-primary role-chip"
                  :title="`scope: ${b.scope_type}`"
                >
                  {{ b.role_name }}
                  <button class="chip-x" @click.stop="onUnbindRole(row, b)">×</button>
                </span>
                <button class="chip chip-neutral add-chip" @click.stop="onBindRole(row)">+ 分配</button>
              </div>
            </template>
            <template #status="{ row }">
              <span class="chip" :class="row.is_active ? 'chip-success' : 'chip-danger'">
                {{ row.is_active ? '启用' : '禁用' }}
              </span>
            </template>
          </DataTable>
        </AppCard>
      </el-tab-pane>

      <!-- 角色 -->
      <el-tab-pane :label="`角色 (${roles.length})`" name="roles">
        <AppCard>
          <template #actions>
            <el-button v-if="can('role.write')" type="primary" @click="openCreateRole">+ 新建角色</el-button>
          </template>
          <div class="role-grid">
            <div v-for="r in roles" :key="r.id" class="role-card">
              <div class="role-card__head">
                <div>
                  <div class="role-card__name">
                    {{ r.name }}
                    <span v-if="r.is_system" class="chip chip-warning">系统</span>
                  </div>
                  <code class="mono role-card__code">{{ r.code }}</code>
                </div>
                <div class="role-card__actions">
                  <el-button v-if="can('role.write')" size="small" text type="primary" @click="openEditRole(r)">编辑</el-button>
                  <el-button
                    size="small"
                    text
                    type="danger"
                    :disabled="r.is_system"
                    @click="onDeleteRole(r)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
              <p class="role-card__desc">{{ r.description || '—' }}</p>
              <div class="role-card__perms">
                <span class="perm-count num">{{ r.permissions.length }}</span>
                <span class="perm-label">项权限</span>
                <button class="link-btn" @click="matrixOpen = matrixOpen === r.id ? null : r.id">
                  {{ matrixOpen === r.id ? '收起' : '查看权限矩阵' }}
                </button>
              </div>
              <transition name="slide">
                <div v-if="matrixOpen === r.id" class="perm-matrix">
                  <div v-for="(perms, cat) in catalog?.permissions" :key="cat" class="perm-cat">
                    <div class="perm-cat__label">{{ cat }}</div>
                    <div class="perm-cat__list">
                      <span
                        v-for="p in perms"
                        :key="p.code"
                        class="perm-pill"
                        :class="{ 'is-on': r.permissions.includes(p.code) }"
                        :title="p.description"
                      >
                        {{ p.name }}
                      </span>
                    </div>
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </AppCard>
      </el-tab-pane>

      <!-- 组织 -->
      <el-tab-pane :label="`组织 (${orgs.length})`" name="orgs">
        <AppCard>
          <template #actions>
            <el-button v-if="can('org.write')" type="primary" @click="openCreateOrg">+ 新建组织</el-button>
          </template>
          <el-table v-if="orgs.length" :data="orgs" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="代码" width="140">
              <template #default="{ row }">
                <code class="mono">{{ row.code }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="parent_id" label="上级" width="90" />
            <el-table-column prop="description" label="描述" min-width="180" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span class="chip" :class="row.is_active ? 'chip-success' : 'chip-neutral'">
                  {{ row.is_active ? '启用' : '禁用' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="openCreateOrg">编辑</el-button>
                <el-button size="small" text type="danger" @click="onDeleteOrg(row as Organization)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState v-else title="暂无组织" description="创建组织用于数据隔离与团队管理" icon="🏢" action-text="创建" @action="openCreateOrg" />
        </AppCard>
      </el-tab-pane>

      <!-- 团队 -->
      <el-tab-pane :label="`团队 (${teams.length})`" name="teams">
        <AppCard>
          <template #actions>
            <el-button v-if="can('team.write')" type="primary" @click="openCreateTeam">+ 新建团队</el-button>
          </template>
          <el-table v-if="teams.length" :data="teams" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="代码" width="140">
              <template #default="{ row }">
                <code class="mono">{{ row.code }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="org_id" label="所属组织" width="110" />
            <el-table-column prop="member_count" label="成员" width="90" align="right" />
            <el-table-column label="操作" width="220">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="viewTeamMembers(row as Team)">成员</el-button>
                <el-button size="small" text type="primary" @click="onAddTeamMember(row as Team)">添加</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState v-else title="暂无团队" description="创建团队便于按小组分配权限" icon="👥" action-text="创建" @action="openCreateTeam" />

          <div v-for="t in teams" :key="`m-${t.id}`">
            <template v-if="teamMembersMap[t.id]">
              <h4 class="team-members-title">{{ t.name }} 成员</h4>
              <el-table :data="teamMembersMap[t.id]" size="small">
                <el-table-column prop="user_id" label="ID" width="80" />
                <el-table-column prop="username" label="用户名" min-width="140" />
                <el-table-column prop="role" label="团队角色" width="120">
                  <template #default="{ row }">
                    <span class="chip chip-primary">{{ row.role }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100">
                  <template #default="{ row }">
                    <el-button size="small" text type="danger" @click="onRemoveTeamMember(t, row as TeamMember)">移出</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>
          </div>
        </AppCard>
      </el-tab-pane>

      <!-- 会话 -->
      <el-tab-pane :label="`会话 (${allSessions.length})`" name="sessions">
        <AppCard title="我的会话">
          <el-table :data="mySessions" size="default">
            <el-table-column label="Session ID" min-width="200">
              <template #default="{ row }">
                <code class="mono">{{ row.session_id.slice(0, 16) }}…</code>
              </template>
            </el-table-column>
            <el-table-column prop="ip_address" label="IP" width="140" />
            <el-table-column prop="device" label="设备" min-width="140" />
            <el-table-column prop="last_used_at" label="最近使用" width="180" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span class="chip" :class="row.is_active ? 'chip-success' : 'chip-neutral'">
                  {{ row.is_active ? '活跃' : '已撤销' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button v-if="can('session.revoke')" size="small" text type="danger" :disabled="!row.is_active" @click="onRevoke(row as Session)">
                  强制下线
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </AppCard>

        <AppCard title="全平台会话" class="mt-3">
          <el-table :data="allSessions" size="default" max-height="320">
            <el-table-column label="Session ID" min-width="200">
              <template #default="{ row }">
                <code class="mono">{{ row.session_id.slice(0, 16) }}…</code>
              </template>
            </el-table-column>
            <el-table-column prop="user_id" label="用户" width="80" />
            <el-table-column prop="ip_address" label="IP" width="140" />
            <el-table-column prop="last_used_at" label="最近使用" width="180" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span class="chip" :class="row.is_active ? 'chip-success' : 'chip-neutral'">
                  {{ row.is_active ? '活跃' : '已撤销' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button v-if="can('session.revoke')" size="small" text type="danger" :disabled="!row.is_active" @click="onRevoke(row as Session)">
                  强制下线
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </AppCard>
      </el-tab-pane>

      <!-- 登录审计 -->
      <el-tab-pane :label="`登录审计 (${attempts.length})`" name="audit">
        <AppCard title="最近登录尝试" subtitle="含失败原因 · 用于排查与风控">
          <el-table :data="attempts" size="default" max-height="500">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column prop="username" label="用户名" width="140" />
            <el-table-column prop="ip_address" label="IP" width="140" />
            <el-table-column label="结果" width="100">
              <template #default="{ row }">
                <span class="chip" :class="row.success ? 'chip-success' : 'chip-danger'">
                  {{ row.success ? '成功' : '失败' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="原因" width="140">
              <template #default="{ row }">
                <span v-if="row.failure_reason" class="chip chip-warning">{{ row.failure_reason }}</span>
                <span v-else>—</span>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-if="!attempts.length"
            title="暂无登录记录"
            description="登录后会记录在这里"
            icon="📋"
            size="sm"
          />
        </AppCard>
      </el-tab-pane>
    </el-tabs>

    <!-- 用户对话框 -->
    <el-dialog v-model="userDialog" :title="userForm.id ? '✎ 编辑用户' : '+ 新建用户'" width="460">
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
            :placeholder="userForm.id ? '留空则不修改' : '至少 8 位含字母和数字'"
          />
        </div>
        <div class="field">
          <label class="field-label">显示名</label>
          <el-input v-model="userForm.display_name" size="large" />
        </div>
        <div class="field">
          <label class="field-label">内置角色</label>
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
        <el-button type="primary" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <!-- 角色对话框（含权限矩阵） -->
    <el-dialog v-model="roleDialog" :title="roleForm.id ? '✎ 编辑角色' : '+ 新建角色'" width="720">
      <div class="dialog-form">
        <div class="field-row">
          <div class="field">
            <label class="field-label">Code</label>
            <el-input v-model="roleForm.code" :disabled="roleForm.id != null" size="large" placeholder="例如 quality_inspector" />
          </div>
          <div class="field">
            <label class="field-label">名称</label>
            <el-input v-model="roleForm.name" size="large" />
          </div>
        </div>
        <div class="field">
          <label class="field-label">描述</label>
          <el-input v-model="roleForm.description" size="large" />
        </div>

        <div class="perm-selector">
          <div class="perm-selector__head">
            <label class="field-label">权限勾选</label>
            <span class="text-subtle">已选 {{ roleForm.permission_codes.length }} / {{ Object.values(catalog?.permissions ?? {}).flat().length }}</span>
          </div>
          <div v-for="(perms, cat) in catalog?.permissions" :key="cat" class="perm-cat">
            <div class="perm-cat__head">
              <button class="perm-cat__toggle" @click="toggleAllInCategory(String(cat))">
                <span class="perm-cat__checkbox" :class="{ 'is-on': isCategoryAllSelected(String(cat)) }">
                  {{ isCategoryAllSelected(String(cat)) ? '✓' : '' }}
                </span>
                <strong>{{ cat }}</strong>
              </button>
            </div>
            <div class="perm-cat__list">
              <button
                v-for="p in perms"
                :key="p.code"
                class="perm-pill"
                :class="{ 'is-on': roleForm.permission_codes.includes(p.code) }"
                :title="p.description"
                @click="togglePermissionInRole(p.code)"
              >
                {{ p.name }}
              </button>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="roleDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>

    <!-- 组织对话框 -->
    <el-dialog v-model="orgDialog" :title="orgForm.id ? '✎ 编辑组织' : '+ 新建组织'" width="460">
      <div class="dialog-form">
        <div class="field">
          <label class="field-label">名称</label>
          <el-input v-model="orgForm.name" size="large" />
        </div>
        <div class="field">
          <label class="field-label">代码</label>
          <el-input v-model="orgForm.code" :disabled="orgForm.id != null" size="large" />
        </div>
        <div class="field">
          <label class="field-label">描述</label>
          <el-input v-model="orgForm.description" size="large" />
        </div>
      </div>
      <template #footer>
        <el-button @click="orgDialog = false">取消</el-button>
        <el-button type="primary" @click="saveOrg">保存</el-button>
      </template>
    </el-dialog>

    <!-- 团队对话框 -->
    <el-dialog v-model="teamDialog" title="+ 新建团队" width="460">
      <div class="dialog-form">
        <div class="field">
          <label class="field-label">名称</label>
          <el-input v-model="teamForm.name" size="large" />
        </div>
        <div class="field">
          <label class="field-label">代码</label>
          <el-input v-model="teamForm.code" size="large" />
        </div>
        <div class="field">
          <label class="field-label">所属组织（可选）</label>
          <el-select v-model="teamForm.org_id" size="large" clearable style="width: 100%">
            <el-option v-for="o in orgs" :key="o.id" :value="o.id" :label="o.name" />
          </el-select>
        </div>
        <div class="field">
          <label class="field-label">描述</label>
          <el-input v-model="teamForm.description" size="large" />
        </div>
      </div>
      <template #footer>
        <el-button @click="teamDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTeam">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mt-3 { margin-top: var(--sp-3); }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-6);
}

.role-list {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}
.role-chip {
  padding-right: 20px;
  position: relative;
}
.chip-x {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px; height: 14px;
  border-radius: var(--r-full);
  border: none;
  background: rgba(0, 0, 0, 0.1);
  color: inherit;
  font-size: 10px;
  line-height: 1;
  cursor: pointer;
}
.add-chip {
  cursor: pointer;
  background: transparent;
  border: 1px dashed var(--border-default);
}
.add-chip:hover {
  border-color: var(--border-accent);
  color: var(--text-accent);
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--sp-3);
}
.role-card {
  padding: var(--sp-4);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
}
.role-card__head {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
}
.role-card__name {
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.role-card__code {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.role-card__actions {
  display: flex;
  gap: 4px;
}
.role-card__desc {
  margin: var(--sp-2) 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.role-card__perms {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
}
.perm-count {
  font-weight: var(--fw-semibold);
  color: var(--text-accent);
}
.perm-label {
  color: var(--text-tertiary);
}
.link-btn {
  background: transparent;
  border: none;
  color: var(--text-accent);
  cursor: pointer;
  font-size: var(--fs-sm);
  padding: 0;
  margin-left: auto;
  text-decoration: underline;
}

.perm-matrix {
  margin-top: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: 1px solid var(--border-default);
}
.perm-cat {
  margin-bottom: var(--sp-2);
}
.perm-cat__label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}
.perm-cat__head {
  margin-bottom: 4px;
}
.perm-cat__toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.perm-cat__checkbox {
  width: 14px; height: 14px;
  border: 1.5px solid var(--border-strong);
  border-radius: 3px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}
.perm-cat__checkbox.is-on {
  background: var(--c-primary-600);
  border-color: var(--c-primary-600);
  color: white;
}
.perm-cat__list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.perm-pill {
  padding: 3px 8px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-full);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.perm-pill:hover {
  border-color: var(--border-accent);
  color: var(--text-accent);
}
.perm-pill.is-on {
  background: var(--c-primary-600);
  color: white;
  border-color: var(--c-primary-600);
}

.perm-selector {
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  padding: var(--sp-3);
}
.perm-selector__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
}

.team-members-title {
  margin: var(--sp-4) 0 var(--sp-2);
  font-size: var(--fs-md);
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

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
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

.slide-enter-active, .slide-leave-active {
  transition: all var(--t-base) var(--ease-standard);
}
.slide-enter-from, .slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
