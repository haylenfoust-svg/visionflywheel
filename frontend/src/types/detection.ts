/** Detection / Task types — mirror backend `app/schemas/detection.py`. */

export interface BBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface Detection {
  id: number
  task_id: number
  item_index: number
  image_path: string
  result_path: string | null
  class_id: number
  class_name: string
  class_name_zh: string | null
  confidence: number
  bbox: BBox
  status: 'pending' | 'corrected' | 'rejected'
  source: 'model' | 'manual'
  created_at: string
}

export interface Task {
  id: number
  type: 'image' | 'batch' | 'video'
  status: 'pending' | 'running' | 'done' | 'failed'
  created_by: string | null
  conf_threshold: number
  iou_threshold: number
  imgsz: number
  weight_id: number | null
  detector_mode: 'yolo' | 'fallback'
  total_items: number
  done_items: number
  inference_ms: number | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface UploadResult {
  task_id: number
  status: string
  image_url: string
  result_url: string | null
  detector_mode: string
  inference_ms: number
  detections: Detection[]
}

export interface DetectionStats {
  total: number
  by_status: Record<string, number>
  by_class: Array<{ class_name: string; class_name_zh: string | null; count: number }>
  today: { detected: number; corrected: number }
  avg_confidence: number
}

export interface DetectParams {
  conf_threshold?: number
  iou_threshold?: number
  imgsz?: number
}
