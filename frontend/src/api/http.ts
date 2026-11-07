import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

import type { ApiResponse } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('vf_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse<unknown>
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      return Promise.reject(new Error(body.message || `error code ${body.code}`))
    }
    return response
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    const status = error.response?.status
    const message = error.response?.data?.message ?? error.message
    if (status === 401) {
      localStorage.removeItem('vf_token')
      localStorage.removeItem('vf_user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(new Error(message))
  },
)

/** Convenience wrapper that unwraps `data` from the standard envelope. */
export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const resp = await http.get<ApiResponse<T>>(url, { params })
  return resp.data.data
}

export async function apiPost<T>(url: string, payload?: unknown): Promise<T> {
  const resp = await http.post<ApiResponse<T>>(url, payload)
  return resp.data.data
}

export async function apiPut<T>(url: string, payload?: unknown): Promise<T> {
  const resp = await http.put<ApiResponse<T>>(url, payload)
  return resp.data.data
}

export async function apiDelete<T>(url: string): Promise<T> {
  const resp = await http.delete<ApiResponse<T>>(url)
  return resp.data.data
}
