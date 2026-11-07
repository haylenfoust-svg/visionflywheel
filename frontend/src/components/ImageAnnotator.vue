<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { BBox, Detection } from '@/types/detection'

/**
 * Canvas-based annotator (PRD FR-3.1 ~ FR-3.5).
 *
 * BBoxes are stored in IMAGE pixel coordinates. The canvas displays at a
 * different size; every pointer interaction maps through `scale` so the
 * numbers we emit always refer to the source image.
 *
 * Interactions:
 *   - click a box          -> select
 *   - drag inside a box    -> move (emits `adjust` on release)
 *   - drag a corner handle -> resize (emits `adjust` on release)
 *   - drag empty canvas    -> draw a new box (emits `add` on release)
 */

const props = withDefaults(
  defineProps<{
    imageSrc: string
    detections: Detection[]
    selectedId?: number | null
    /** When false, drawing new boxes is disabled (read-only mode). */
    interactive?: boolean
  }>(),
  { selectedId: null, interactive: true },
)

const emit = defineEmits<{
  (e: 'select', id: number | null): void
  (e: 'adjust', id: number, bbox: BBox): void
  (e: 'add', bbox: BBox): void
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const wrapRef = ref<HTMLDivElement | null>(null)
const img = ref<HTMLImageElement | null>(null)

const naturalSize = ref({ w: 0, h: 0 })
const displaySize = ref({ w: 0, h: 0 })
const scale = ref(1)

type Mode = 'idle' | 'moving' | 'resizing' | 'drawing'
const mode = ref<Mode>('idle')
const activeId = ref<number | null>(null)
const dragStart = ref({ x: 0, y: 0 })
const dragOriginalBox = ref<BBox | null>(null)
const dragHandle = ref<string | null>(null) // 'nw' | 'ne' | 'sw' | 'se'
const draftBox = ref<BBox | null>(null)

const HANDLE_SIZE = 8 // display px

const canDraw = computed(() => props.interactive)

// ---------- lifecycle ----------
onMounted(() => {
  const image = new Image()
  image.onload = () => {
    img.value = image
    naturalSize.value = { w: image.naturalWidth, h: image.naturalHeight }
    measure()
    render()
  }
  image.src = props.imageSrc
  window.addEventListener('resize', measure)
})

onBeforeUnmount(() => window.removeEventListener('resize', measure))

watch(() => props.detections, () => render(), { deep: true })
watch(() => props.selectedId, () => render())

function measure() {
  const wrap = wrapRef.value
  const image = img.value
  if (!wrap || !image) return
  const maxW = wrap.clientWidth
  const maxH = 560
  const ratio = Math.min(maxW / image.naturalWidth, maxH / image.naturalHeight, 1)
  displaySize.value = {
    w: Math.round(image.naturalWidth * ratio),
    h: Math.round(image.naturalHeight * ratio),
  }
  scale.value = ratio
  const canvas = canvasRef.value
  if (canvas) {
    canvas.width = displaySize.value.w
    canvas.height = displaySize.value.h
  }
  render()
}

// ---------- coordinate helpers ----------
function toDisplay(b: BBox): BBox {
  return {
    x1: b.x1 * scale.value,
    y1: b.y1 * scale.value,
    x2: b.x2 * scale.value,
    y2: b.y2 * scale.value,
  }
}

function pointFromEvent(ev: MouseEvent): { x: number; y: number } {
  const rect = canvasRef.value!.getBoundingClientRect()
  return { x: ev.clientX - rect.left, y: ev.clientY - rect.top }
}

function hitTest(p: { x: number; y: number }): { id: number | null; handle: string | null } {
  // Handles first (on top of the selected box)
  const selected = props.detections.find((d) => d.id === props.selectedId)
  if (selected) {
    const d = toDisplay(selected.bbox)
    const corners: Array<[string, number, number]> = [
      ['nw', d.x1, d.y1],
      ['ne', d.x2, d.y1],
      ['sw', d.x1, d.y2],
      ['se', d.x2, d.y2],
    ]
    for (const [name, cx, cy] of corners) {
      if (Math.abs(p.x - cx) <= HANDLE_SIZE && Math.abs(p.y - cy) <= HANDLE_SIZE) {
        return { id: selected.id, handle: name }
      }
    }
  }
  // Box interiors (topmost first — render order is bottom-up, so iterate reverse)
  for (let i = props.detections.length - 1; i >= 0; i -= 1) {
    const det = props.detections[i]
    const d = toDisplay(det.bbox)
    if (p.x >= d.x1 && p.x <= d.x2 && p.y >= d.y1 && p.y <= d.y2) {
      return { id: det.id, handle: null }
    }
  }
  return { id: null, handle: null }
}

function clampBox(b: BBox): BBox {
  const w = naturalSize.value.w
  const h = naturalSize.value.h
  return {
    x1: Math.max(0, Math.min(b.x1, w - 1)),
    y1: Math.max(0, Math.min(b.y1, h - 1)),
    x2: Math.max(1, Math.min(b.x2, w)),
    y2: Math.max(1, Math.min(b.y2, h)),
  }
}

// ---------- render ----------
function render() {
  const canvas = canvasRef.value
  const image = img.value
  if (!canvas || !image) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height)

  for (const det of props.detections) {
    const d = toDisplay(det.bbox)
    const isSelected = det.id === props.selectedId
    const color = det.status === 'rejected' ? '#c62828' : det.status === 'corrected' ? '#2e7d32' : '#1976d2'
    ctx.strokeStyle = color
    ctx.lineWidth = isSelected ? 3 : 2
    ctx.strokeRect(d.x1, d.y1, d.x2 - d.x1, d.y2 - d.y1)

    const label = `${det.class_name_zh || det.class_name} ${(det.confidence * 100).toFixed(0)}%`
    ctx.font = '12px sans-serif'
    const tw = ctx.measureText(label).width
    const th = 16
    const ty = Math.max(0, d.y1 - th)
    ctx.fillStyle = color
    ctx.fillRect(d.x1, ty, tw + 8, th)
    ctx.fillStyle = '#ffffff'
    ctx.fillText(label, d.x1 + 4, ty + 12)

    if (isSelected && props.interactive) {
      ctx.fillStyle = '#ffffff'
      ctx.strokeStyle = color
      const hs = HANDLE_SIZE / 2
      const corners: Array<[number, number]> = [
        [d.x1, d.y1],
        [d.x2, d.y1],
        [d.x1, d.y2],
        [d.x2, d.y2],
      ]
      for (const [cx, cy] of corners) {
        ctx.fillRect(cx - hs, cy - hs, HANDLE_SIZE, HANDLE_SIZE)
        ctx.strokeRect(cx - hs, cy - hs, HANDLE_SIZE, HANDLE_SIZE)
      }
    }
  }

  if (draftBox.value) {
    const d = toDisplay(draftBox.value)
    ctx.setLineDash([6, 4])
    ctx.strokeStyle = '#1976d2'
    ctx.lineWidth = 2
    ctx.strokeRect(d.x1, d.y1, d.x2 - d.x1, d.y2 - d.y1)
    ctx.setLineDash([])
    ctx.fillStyle = 'rgba(25, 118, 210, 0.12)'
    ctx.fillRect(d.x1, d.y1, d.x2 - d.x1, d.y2 - d.y1)
  }
}

// ---------- pointer events ----------
function onMouseDown(ev: MouseEvent) {
  if (!canDraw.value) return
  const p = pointFromEvent(ev)
  const hit = hitTest(p)

  if (hit.handle) {
    mode.value = 'resizing'
    activeId.value = hit.id
    dragHandle.value = hit.handle
    const det = props.detections.find((d) => d.id === hit.id)
    dragOriginalBox.value = det ? { ...det.bbox } : null
  } else if (hit.id !== null) {
    mode.value = 'moving'
    activeId.value = hit.id
    dragHandle.value = null
    const det = props.detections.find((d) => d.id === hit.id)
    dragOriginalBox.value = det ? { ...det.bbox } : null
    emit('select', hit.id)
  } else {
    mode.value = 'drawing'
    activeId.value = null
    dragOriginalBox.value = null
    draftBox.value = { x1: p.x / scale.value, y1: p.y / scale.value, x2: p.x / scale.value, y2: p.y / scale.value }
    emit('select', null)
  }
  dragStart.value = p
}

function onMouseMove(ev: MouseEvent) {
  if (mode.value === 'idle') return
  const p = pointFromEvent(ev)
  const dx = p.x - dragStart.value.x
  const dy = p.y - dragStart.value.y
  const idx = dx / scale.value
  const idy = dy / scale.value

  if (mode.value === 'drawing' && draftBox.value) {
    draftBox.value = clampBox({
      x1: Math.min(draftBox.value.x1, draftBox.value.x1 + idx),
      y1: Math.min(draftBox.value.y1, draftBox.value.y1 + idy),
      x2: Math.max(draftBox.value.x1, draftBox.value.x1 + idx),
      y2: Math.max(draftBox.value.y1, draftBox.value.y1 + idy),
    })
  } else if (mode.value === 'moving' && dragOriginalBox.value && activeId.value !== null) {
    const b = dragOriginalBox.value
    const det = props.detections.find((d) => d.id === activeId.value)
    if (det) {
      det.bbox = clampBox({
        x1: b.x1 + idx,
        y1: b.y1 + idy,
        x2: b.x2 + idx,
        y2: b.y2 + idy,
      })
    }
  } else if (mode.value === 'resizing' && dragOriginalBox.value && activeId.value !== null) {
    const b = dragOriginalBox.value
    const det = props.detections.find((d) => d.id === activeId.value)
    if (det) {
      const next: BBox = { ...b }
      if (dragHandle.value?.includes('n')) next.y1 = b.y1 + idy
      if (dragHandle.value?.includes('s')) next.y2 = b.y2 + idy
      if (dragHandle.value?.includes('w')) next.x1 = b.x1 + idx
      if (dragHandle.value?.includes('e')) next.x2 = b.x2 + idx
      det.bbox = clampBox(next)
    }
  }
  render()
}

function onMouseUp() {
  if (mode.value === 'idle') return

  if (mode.value === 'drawing' && draftBox.value) {
    const b = draftBox.value
    const minSide = 4 / scale.value
    if (b.x2 - b.x1 > minSide && b.y2 - b.y1 > minSide) {
      emit('add', { ...b })
    }
    draftBox.value = null
  } else if ((mode.value === 'moving' || mode.value === 'resizing') && activeId.value !== null) {
    const det = props.detections.find((d) => d.id === activeId.value)
    const orig = dragOriginalBox.value
    if (det && orig && (det.bbox.x1 !== orig.x1 || det.bbox.y1 !== orig.y1 || det.bbox.x2 !== orig.x2 || det.bbox.y2 !== orig.y2)) {
      emit('adjust', det.id, { ...det.bbox })
    }
    if (det && orig) {
      // Restore optimistic change; caller decides what to persist
      det.bbox = orig
    }
  }

  mode.value = 'idle'
  activeId.value = null
  dragHandle.value = null
  dragOriginalBox.value = null
  render()
}
</script>

<template>
  <div ref="wrapRef" class="annotator-wrap">
    <canvas
      ref="canvasRef"
      class="annotator-canvas"
      :class="{ interactive: canDraw, drawing: mode === 'drawing' }"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseUp"
    />
    <div v-if="!detections.length" class="empty-hint">拖拽空白区域可新增一个框</div>
  </div>
</template>

<style scoped>
.annotator-wrap {
  position: relative;
  width: 100%;
  background: var(--vf-bg);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius);
  overflow: hidden;
}
.annotator-canvas {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
}
.annotator-canvas.interactive {
  cursor: crosshair;
}
.empty-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vf-ink-muted);
  font-size: 13px;
  pointer-events: none;
}
</style>
