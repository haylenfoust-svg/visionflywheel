/** Stats API client (M5.2). */

import { apiGet } from './http'

export interface DashboardOverview {
  totals: {
    tasks: number
    detections: number
    corrections: number
    datasets: number
    weights: number
    open_tickets: number
  }
  today: {
    tasks: number
    detections: number
    corrections: number
  }
  by_status: Record<string, number>
  by_task_status: Record<string, number>
  by_class: Array<{ class_name: string; class_name_zh: string | null; count: number }>
  by_action: Record<string, number>
  per_day: Array<{ date: string; count: number }>
  corr_per_day: Array<{ date: string; count: number }>
  avg_confidence: number
  recent_tasks: Array<{
    id: number
    type: string
    status: string
    detector_mode: string
    total_items: number
    detections: number
    created_at: string | null
  }>
  recent_corrections: Array<{
    id: number
    action: string
    detection_id: number | null
    operator: string | null
    comment: string | null
    created_at: string | null
  }>
}

export interface HealthDetail {
  app: string
  version: string
  db: string
  detector_mode: string
  detector_available: boolean
  fallback_enabled: boolean
  database_url_scheme: string
  user_count: number
}

export async function overview(): Promise<DashboardOverview> {
  return apiGet<DashboardOverview>('/api/stats/overview')
}

export async function healthDetail(): Promise<HealthDetail> {
  return apiGet<HealthDetail>('/api/stats/health-detail')
}
