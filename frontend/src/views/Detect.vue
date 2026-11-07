<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { uploadAndDetect } from '@/api/tasks'
import DetectionTable from '@/components/DetectionTable.vue'
import UploadDrop from '@/components/UploadDrop.vue'
import type { Detection, UploadResult } from '@/types/detection'

const params = reactive({
  conf_threshold: 0.5,
  iou_threshold: 0.45,
  imgsz: 640,
})

const loading = ref(false)
const result = ref<UploadResult | null>(null)
const selected = ref<Detection | null>(null)
const previewUrl = ref<string>('')

const detectorTag = computed(() => {
  const mode = result.value?.detector_mode
  if (mode === 'yolo') return { text: 'YOLO', type: 'success' as const }
  if (mode === 'fallback') return { text: '降级检测器', type: 'warning' as const }
  return null
})

async function onFile(file: File) {
  if (loading.value) return
  loading.value = true
  selected.value = null
  try {
    const res = await uploadAndDetect(file, {
      conf_threshold: params.conf_threshold,
      iou_threshold: params.iou_threshold,
      imgsz: params.imgsz,
    })
    result.value = res
    previewUrl.value = res.result_url || res.image_url
    if (res.detector_mode === 'fallback') {
      ElMessage.warning('当前使用降级检测器（torch/ultralytics 未安装）。闭环可跑通，但精度有限。')
    } else {
      ElMessage.success(`识别完成，共 ${res.detections.length} 个目标`)
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '识别失败')
  } finally {
    loading.value = false
  }
}

function onSelectDetection(d: Detection) {
  selected.value = d
}
</script>

<template>
  <div class="page detect">
    <h2>识别</h2>
    <p class="lead">上传一张图片，看模型框出什么。看错了之后可以去「校正」页面修改（M3）。</p>

    <div class="grid">
      <section class="panel">
        <h3>上传</h3>
        <UploadDrop :disabled="loading" @select="onFile" />

        <div class="params">
          <div class="field">
            <label>置信度阈值 (conf)</label>
            <el-slider v-model="params.conf_threshold" :min="0" :max="1" :step="0.05" show-input />
          </div>
          <div class="field">
            <label>IoU 阈值</label>
            <el-slider v-model="params.iou_threshold" :min="0" :max="1" :step="0.05" show-input />
          </div>
          <div class="field">
            <label>推理尺寸 (imgsz)</label>
            <el-select v-model="params.imgsz" size="small" style="width: 140px">
              <el-option :value="320" label="320" />
              <el-option :value="640" label="640" />
              <el-option :value="960" label="960" />
              <el-option :value="1280" label="1280" />
            </el-select>
          </div>
        </div>

        <el-alert
          v-if="detectorTag?.type === 'warning'"
          type="warning"
          :closable="false"
          title="降级检测器已启用"
          description="未检测到 ultralytics/torch，已切到规则检测器。闭环（识别→校正→导出）可完整跑通，精度有限。安装 `pip install -r requirements-ml.txt` 可切回真实 YOLO。"
        />
      </section>

      <section class="panel">
        <h3>结果</h3>
        <div v-if="loading" class="loading">
          <el-icon class="is-loading" :size="24"><i class="el-icon-loading" /></el-icon>
          <p>识别中…</p>
        </div>

        <template v-else-if="result">
          <div class="result-header">
            <el-tag v-if="detectorTag" :type="detectorTag.type" size="small">
              {{ detectorTag.text }}
            </el-tag>
            <span class="meta">
              任务 #{{ result.task_id }} · {{ result.inference_ms.toFixed(0) }}ms ·
              {{ result.detections.length }} 个目标
            </span>
          </div>

          <div class="canvas-wrap">
            <img v-if="previewUrl" :src="previewUrl" alt="识别结果" class="preview" />
            <el-empty v-else description="无结果图" />
          </div>

          <h4>检测明细</h4>
          <DetectionTable :detections="result.detections" @select="onSelectDetection" />

          <el-descriptions v-if="selected" :column="1" size="small" class="detail" title="选中项">
            <el-descriptions-item label="ID">{{ selected.id }}</el-descriptions-item>
            <el-descriptions-item label="类别（英文）">{{ selected.class_name }}</el-descriptions-item>
            <el-descriptions-item label="类别（中文）">{{ selected.class_name_zh ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="置信度">{{ (selected.confidence * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item label="坐标">
              {{ selected.bbox.x1.toFixed(0) }}, {{ selected.bbox.y1.toFixed(0) }},
              {{ selected.bbox.x2.toFixed(0) }}, {{ selected.bbox.y2.toFixed(0) }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">{{ selected.status }}</el-descriptions-item>
          </el-descriptions>
        </template>

        <el-empty v-else description="上传一张图片开始识别" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.lead {
  color: var(--vf-ink-muted);
}
.grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 20px;
  align-items: start;
}
.panel {
  background: var(--vf-surface);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-lg);
  padding: 18px;
}
.panel h3 {
  margin: 0 0 12px;
  font-size: 14px;
}
.params {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.field label {
  display: block;
  font-size: 12px;
  color: var(--vf-ink-muted);
  margin-bottom: 4px;
}
.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.meta {
  color: var(--vf-ink-muted);
  font-size: 12px;
}
.canvas-wrap {
  background: var(--vf-bg);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius);
  overflow: hidden;
  margin-bottom: 12px;
}
.preview {
  display: block;
  width: 100%;
  height: auto;
  max-height: 480px;
  object-fit: contain;
}
.loading {
  text-align: center;
  padding: 32px;
  color: var(--vf-ink-muted);
}
.detail {
  margin-top: 12px;
}
</style>
