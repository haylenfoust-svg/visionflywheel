/** Types mirroring backend `app/schemas/` — keep in sync with docs/API.md. */

export interface User {
  id: number
  username: string
  role: 'user' | 'admin'
  is_active: boolean
  display_name?: string | null
  created_at: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenOut {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
  request_id?: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface ConfigValue {
  value: unknown
  source: 'db' | 'env' | 'default'
  default: unknown
}

export interface ConfigMap {
  values: Record<string, ConfigValue>
}

export interface Health {
  status: string
  version: string
  detector_mode: string
  db: string
}

export interface SystemInfo {
  version: string
  detector_mode: string
  default_weight_id: number | null
  enable_fallback_detector: boolean
  role: string
}
