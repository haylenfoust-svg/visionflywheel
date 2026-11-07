/** Quality metrics API (AI-2). */

import { apiGet, apiPost } from './http'

export interface QualityRates {
  false_positive_rate: number
  miss_rate_proxy: number
  correction_rate: number
}

export interface QualityWindow {
  days: number
  detections: { value: number; delta: number; pct: number }
  corrections: { value: number; delta: number; pct: number }
}

export interface QualityMetrics {
  totals: {
    detections: number
    rejected: number
    corrected: number
    pending: number
    added: number
  }
  rates: QualityRates
  trend: {
    detections: Array<{ date: string; count: number }>
    corrections: Array<{ date: string; count: number }>
  }
  by_action: Record<string, number>
  window: QualityWindow
}

export async function qualityMetrics(days = 30): Promise<QualityMetrics> {
  return apiGet<QualityMetrics>('/api/stats/quality', { days })
}

export interface WeightSnapshot {
  id: number
  filename: string
  source: string
  dataset_version: string | null
  holdout_map: number | null
  class_count: number | null
  note: string | null
  is_default: boolean
  created_at: string | null
  path: string
}

export interface WeightComparison {
  base: WeightSnapshot
  target: WeightSnapshot
  delta: {
    holdout_map: number | null
    improved: boolean
    regressed: boolean
    same_dataset: boolean
    same_classes: boolean
  }
}

export async function weightHistory(): Promise<WeightSnapshot[]> {
  return apiGet<WeightSnapshot[]>('/api/weights/history')
}

export async function compareWeights(base: number, target: number): Promise<WeightComparison> {
  return apiGet<WeightComparison>('/api/weights/compare', { base, target })
}

export async function weightTraining(weightId: number): Promise<{
  weight: WeightSnapshot
  training_runs: Array<{
    id: number
    status: string
    epochs: number
    imgsz: number
    batch: number
    holdout_map: number | null
    created_at: string | null
  }>
}> {
  return apiGet(`/api/weights/${weightId}/training`)
}

export async function rollbackWeight(weightId: number): Promise<{
  weight_id: number
  filename: string
  is_default: boolean
  reloaded_in_ms: number
  requires_restart: boolean
  dataset_version: string | null
  holdout_map: number | null
  rolled_back: boolean
}> {
  return apiPost(`/api/weights/${weightId}/rollback`)
}

