import { apiGet, apiPost, apiPut } from './http'

import type { SystemInfo, TokenOut, User } from '@/types'

export async function login(username: string, password: string): Promise<TokenOut> {
  return apiPost<TokenOut>('/api/auth/login', { username, password })
}

export async function me(): Promise<User> {
  return apiGet<User>('/api/auth/me')
}

export async function listUsers(): Promise<User[]> {
  return apiGet<User[]>('/api/auth/users')
}

export async function createUser(payload: {
  username: string
  password: string
  role: string
  display_name?: string
}): Promise<User> {
  return apiPost<User>('/api/auth/users', payload)
}

export async function updateUser(id: number, payload: Partial<{ password: string; role: string; is_active: boolean; display_name: string }>): Promise<User> {
  return apiPut<User>(`/api/auth/users/${id}`, payload)
}

export async function systemInfo(): Promise<SystemInfo> {
  return apiGet<SystemInfo>('/api/system/info')
}

export async function health(): Promise<{ status: string; version: string; detector_mode: string; db: string }> {
  return apiGet('/api/system/health')
}
