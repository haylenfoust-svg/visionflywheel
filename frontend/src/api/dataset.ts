import { apiGet, apiPost, apiPut, apiDelete, http } from './http'

import type { Page } from '@/types'

export interface DatasetExportResult {
  dataset_version: string
  path: string
  train_images: number
  val_images: number
  holdout_images: number
  total_labels: number
  class_names: string[]
}

export interface DatasetExportRow {
  id: number
  dataset_version: string
  name: string | null
  total_images: number
  total_labels: number
  train_images: number
  val_images: number
  holdout_images: number
  class_names: string
  val_ratio: number
  seed: number
  status: string
  path: string
  created_by: string | null
  created_at: string
}

export interface DatasetPending {
  pending_images: number
  holdout_images: number
  sample_preview: string[]
}

export interface DatasetSample {
  id: number
  image_path: string
  split: string
  dataset_version: string | null
  is_frozen: boolean
  created_at: string
}

export interface Weight {
  id: number
  filename: string
  path: string
  is_default: boolean
  source: string
  dataset_version: string | null
  holdout_map: number | null
  class_count: number | null
  note: string | null
  created_at: string
}

export interface TrainRun {
  id: number
  dataset_version: string
  base_weight: string
  name: string | null
  epochs: number
  imgsz: number
  batch: number
  status: string
  progress: number
  best_weight_path: string | null
  holdout_map: number | null
  error_message: string | null
  started_by: string | null
  created_at: string
  log_tail?: string | null
}

// ---------- Dataset ----------
export async function datasetPending(): Promise<DatasetPending> {
  return apiGet<DatasetPending>('/api/dataset/pending')
}

export async function datasetExport(payload: {
  name?: string
  val_ratio?: number
  include_rejected?: boolean
  seed?: number
}): Promise<DatasetExportResult> {
  return apiPost<DatasetExportResult>('/api/dataset/export', payload)
}

export async function datasetList(page = 1, pageSize = 20): Promise<Page<DatasetExportRow>> {
  return apiGet<Page<DatasetExportRow>>('/api/dataset', { page, page_size: pageSize })
}

export async function datasetHoldout(page = 1, pageSize = 50): Promise<Page<DatasetSample>> {
  return apiGet<Page<DatasetSample>>('/api/dataset/holdout', { page, page_size: pageSize })
}

export function datasetDownloadUrl(version: string): string {
  return `/api/dataset/${version}/download`
}

export async function datasetDownload(version: string): Promise<Blob> {
  const resp = await http.get(datasetDownloadUrl(version), { responseType: 'blob' })
  return resp.data
}

// ---------- Weights ----------
export async function listWeights(): Promise<Weight[]> {
  return apiGet<Weight[]>('/api/weights')
}

export async function uploadWeight(file: File, note?: string): Promise<Weight> {
  const form = new FormData()
  form.append('file', file)
  if (note) form.append('note', note)
  const resp = await http.post('/api/weights/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000,
  })
  return resp.data.data
}

export async function setDefaultWeight(id: number): Promise<{
  weight_id: number
  filename: string
  is_default: boolean
  reloaded_in_ms: number
  requires_restart: boolean
}> {
  return apiPut(`/api/weights/${id}/default`)
}

export async function deleteWeight(id: number): Promise<void> {
  await apiDelete(`/api/weights/${id}`)
}

// ---------- Training ----------
export async function startTraining(payload: {
  dataset_version: string
  base_weight?: string
  epochs?: number
  imgsz?: number
  batch?: number
  name?: string
}): Promise<TrainRun> {
  return apiPost<TrainRun>('/api/train', payload)
}

export async function listTraining(page = 1, pageSize = 20): Promise<Page<TrainRun>> {
  return apiGet<Page<TrainRun>>('/api/train', { page, page_size: pageSize })
}

export async function getTraining(id: number): Promise<TrainRun> {
  return apiGet<TrainRun>(`/api/train/${id}`)
}

export async function cancelTraining(id: number): Promise<TrainRun> {
  return apiPost<TrainRun>(`/api/train/${id}/cancel`)
}
