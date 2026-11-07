/** RBAC API client (B端-7). */

import { apiGet, apiPost, apiPut, apiDelete } from './http'

export interface Permission {
  code: string
  name: string
  category: string
  description: string
}

export interface PermissionCategory {
  key: string
  label: string
}

export interface PermissionCatalog {
  categories: PermissionCategory[]
  permissions: Record<string, Permission[]>
}

export interface Role {
  id: number
  code: string
  name: string
  description: string | null
  is_system: boolean
  is_active: boolean
  permissions: string[]
}

export interface UserRoleBinding {
  role_id: number
  role_code: string
  role_name: string
  scope_type: 'global' | 'org' | 'team'
  scope_id: number | null
}

export interface Organization {
  id: number
  name: string
  code: string
  parent_id: number | null
  description: string | null
  is_active: boolean
}

export interface Team {
  id: number
  name: string
  code: string
  org_id: number | null
  description: string | null
  is_active: boolean
  member_count: number
}

export interface TeamMember {
  user_id: number
  username: string
  display_name: string | null
  role: 'owner' | 'admin' | 'member' | 'viewer'
}

export interface Session {
  session_id: string
  user_id: number
  device: string | null
  ip_address: string | null
  user_agent: string | null
  created_at: string | null
  last_used_at: string | null
  expires_at: string | null
  is_active: boolean
  revoked_reason: string | null
}

// ---- permissions ----
export async function listPermissions(): Promise<PermissionCatalog> {
  return apiGet<PermissionCatalog>('/api/rbac/permissions')
}

export async function myPermissions(): Promise<{ codes: string[]; is_admin: boolean }> {
  return apiGet('/api/rbac/my-permissions')
}

// ---- roles ----
export async function listRoles(): Promise<Role[]> {
  return apiGet<Role[]>('/api/rbac/roles')
}

export async function createRole(payload: {
  code: string
  name: string
  description?: string
  permission_codes: string[]
}): Promise<{ id: number; code: string; name: string }> {
  return apiPost('/api/rbac/roles', payload)
}

export async function updateRole(
  id: number,
  payload: {
    name?: string
    description?: string
    is_active?: boolean
    permission_codes?: string[]
  },
): Promise<{ id: number; code: string; permissions: string[] }> {
  return apiPut(`/api/rbac/roles/${id}`, payload)
}

export async function deleteRole(id: number): Promise<void> {
  await apiDelete(`/api/rbac/roles/${id}`)
}

// ---- user role assignment ----
export async function getUserRoles(userId: number): Promise<UserRoleBinding[]> {
  return apiGet<UserRoleBinding[]>(`/api/rbac/users/${userId}/roles`)
}

export async function assignRole(
  userId: number,
  payload: { role_code: string; scope_type?: string; scope_id?: number | null },
): Promise<void> {
  await apiPost(`/api/rbac/users/${userId}/roles`, payload)
}

export async function unassignRole(userId: number, roleId: number): Promise<void> {
  await apiDelete(`/api/rbac/users/${userId}/roles/${roleId}`)
}

// ---- orgs ----
export async function listOrgs(): Promise<Organization[]> {
  return apiGet<Organization[]>('/api/rbac/orgs')
}

export async function createOrg(payload: {
  name: string
  code: string
  parent_id?: number | null
  description?: string
}): Promise<{ id: number; code: string; name: string }> {
  return apiPost('/api/rbac/orgs', payload)
}

export async function updateOrg(id: number, payload: Partial<Organization>): Promise<void> {
  await apiPut(`/api/rbac/orgs/${id}`, payload)
}

export async function deleteOrg(id: number): Promise<void> {
  await apiDelete(`/api/rbac/orgs/${id}`)
}

// ---- teams ----
export async function listTeams(): Promise<Team[]> {
  return apiGet<Team[]>('/api/rbac/teams')
}

export async function createTeam(payload: {
  name: string
  code: string
  org_id?: number | null
  description?: string
}): Promise<{ id: number; code: string; name: string }> {
  return apiPost('/api/rbac/teams', payload)
}

export async function teamMembers(teamId: number): Promise<TeamMember[]> {
  return apiGet<TeamMember[]>(`/api/rbac/teams/${teamId}/members`)
}

export async function addTeamMember(
  teamId: number,
  payload: { user_id: number; role?: string },
): Promise<void> {
  await apiPost(`/api/rbac/teams/${teamId}/members`, payload)
}

export async function removeTeamMember(teamId: number, userId: number): Promise<void> {
  await apiDelete(`/api/rbac/teams/${teamId}/members/${userId}`)
}

// ---- sessions ----
export async function listMySessions(): Promise<Session[]> {
  return apiGet<Session[]>('/api/auth/sessions')
}

export async function listAllSessions(): Promise<Session[]> {
  return apiGet<Session[]>('/api/auth/sessions/all')
}

export async function revokeSession(sessionId: string): Promise<void> {
  await apiDelete(`/api/auth/sessions/${sessionId}`)
}

// ---- login attempts ----
export interface LoginAttempt {
  id: number
  username: string
  ip_address: string | null
  success: boolean
  failure_reason: string | null
  created_at: string | null
}

export async function listLoginAttempts(limit = 50): Promise<LoginAttempt[]> {
  return apiGet<LoginAttempt[]>('/api/auth/login-attempts', { limit })
}
