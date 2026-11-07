import { apiGet } from './http'
import { http } from './http'

import type { ApiResponse, Page } from '@/types'
import type { Detection, DetectionStats, DetectParams, Task, UploadResult } from '@/types/detection'

export async function uploadAndDetect(
  file: File,
  params: DetectParams = {},
): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  if (params.conf_threshold != null) form.append('conf_threshold', String(params.conf_threshold))
  if (params.iou_threshold != null) form.append('iou_threshold', String(params.iou_threshold))
  if (params.imgsz != null) form.append('imgsz', String(params.imgsz))

  const resp = await http.post<ApiResponse<UploadResult>>('/api/tasks/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return resp.data.data
}

export async function listTasks(opts: { page?: number; pageSize?: number; mine?: boolean } = {}): Promise<Page<Task>> {
  const params: Record<string, unknown> = {}
  if (opts.page) params.page = opts.page
  if (opts.pageSize) params.page_size = opts.pageSize
  if (opts.mine) params.mine = true
  return apiGet<Page<Task>>('/api/tasks', params)
}

export async function getTask(taskId: number): Promise<Task> {
  return apiGet<Task>(`/api/tasks/${taskId}`)
}

export async function getTaskDetections(taskId: number): Promise<Detection[]> {
  return apiGet<Detection[]>(`/api/tasks/${taskId}/detections`)
}

export async function getStats(): Promise<DetectionStats> {
  return apiGet<DetectionStats>('/api/detections/stats')
}

export async function getDetection(detectionId: number): Promise<Detection> {
  return apiGet<Detection>(`/api/detections/${detectionId}`)
}
