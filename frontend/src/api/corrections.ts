import { apiGet, apiPost, apiPut } from './http'

import type { Page } from '@/types'
import type { BBox } from '@/types/detection'

export type CorrectionAction = 'confirm' | 'relabel' | 'false_positive' | 'adjust' | 'add' | 'undo'

export interface CorrectionResult {
  correction_id: number
  detection_id: number | null
  action: CorrectionAction
  old_value: string | null
  new_value: string | null
  detection_status: string | null
  created_at: string
}

export interface CorrectionRow {
  id: number
  detection_id: number | null
  task_id: number
  action: CorrectionAction
  old_value: string | null
  new_value: string | null
  undo_of: number | null
  operator: string | null
  comment: string | null
  created_at: string
}

export interface Feedback {
  id: number
  detection_id: number | null
  task_id: number | null
  username: string | null
  content: string
  status: 'open' | 'replied' | 'resolved' | 'rejected'
  reply: string | null
  replied_by: string | null
  created_at: string
  updated_at: string
}

export interface CorrectionPayload {
  action: CorrectionAction
  detection_id?: number | null
  task_id?: number | null
  new_class_name?: string | null
  new_bbox?: BBox | null
  comment?: string | null
  undo_of?: number | null
}

export async function createCorrection(payload: CorrectionPayload): Promise<CorrectionResult> {
  return apiPost<CorrectionResult>('/api/corrections', payload)
}

export async function createBatch(items: CorrectionPayload[]): Promise<CorrectionResult[]> {
  return apiPost<CorrectionResult[]>('/api/corrections/batch', { items })
}

export async function undo(correctionId?: number): Promise<CorrectionResult> {
  return apiPost<CorrectionResult>('/api/corrections/undo', { correction_id: correctionId ?? null })
}

export async function listAudit(params: {
  taskId?: number
  detectionId?: number
  operator?: string
  page?: number
  pageSize?: number
} = {}): Promise<Page<CorrectionRow>> {
  const q: Record<string, unknown> = {}
  if (params.taskId != null) q.task_id = params.taskId
  if (params.detectionId != null) q.detection_id = params.detectionId
  if (params.operator) q.operator = params.operator
  if (params.page) q.page = params.page
  if (params.pageSize) q.page_size = params.pageSize
  return apiGet<Page<CorrectionRow>>('/api/corrections/audit', q)
}

export async function createFeedback(payload: {
  content: string
  detection_id?: number
  task_id?: number
}): Promise<Feedback> {
  return apiPost<Feedback>('/api/feedback', payload)
}

export async function listFeedback(params: {
  status?: string
  mine?: boolean
  page?: number
  pageSize?: number
} = {}): Promise<Page<Feedback>> {
  const q: Record<string, unknown> = {}
  if (params.status) q.status = params.status
  if (params.mine) q.mine = true
  if (params.page) q.page = params.page
  if (params.pageSize) q.page_size = params.pageSize
  return apiGet<Page<Feedback>>('/api/feedback', q)
}

export async function replyFeedback(id: number, reply: string): Promise<Feedback> {
  return apiPut<Feedback>(`/api/feedback/${id}/reply`, { reply })
}

export async function updateFeedbackStatus(id: number, status: string): Promise<Feedback> {
  return apiPut<Feedback>(`/api/feedback/${id}/status`, { status })
}
