<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
    accept?: string
  }>(),
  {
    disabled: false,
    accept: 'image/png,image/jpeg,image/jpg,image/bmp,image/webp',
  },
)

const emit = defineEmits<{
  (e: 'select', file: File): void
}>()

const isDragging = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

function onPick() {
  if (props.disabled) return
  inputRef.value?.click()
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    emit('select', file)
  }
  target.value = ''
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  if (props.disabled) return
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('只支持图片文件')
    return
  }
  emit('select', file)
}
</script>

<template>
  <div
    class="upload-drop"
    :class="{ dragging: isDragging, disabled }"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
    @click="onPick"
  >
    <input ref="inputRef" type="file" :accept="accept" class="hidden-input" @change="onFileChange" />
    <div class="icon">📁</div>
    <div class="text">
      <p class="main">拖拽图片到这里，或 <span class="link">点击选择</span></p>
      <p class="hint">支持 JPG / PNG / BMP / WebP，单张 ≤ 20 MB</p>
    </div>
  </div>
</template>

<style scoped>
.upload-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 36px 24px;
  border: 2px dashed var(--vf-border);
  border-radius: var(--vf-radius-lg);
  background: var(--vf-surface);
  cursor: pointer;
  transition: all 0.15s ease;
}
.upload-drop:hover {
  border-color: var(--vf-accent);
  background: var(--vf-accent-soft);
}
.upload-drop.dragging {
  border-color: var(--vf-accent);
  background: var(--vf-accent-soft);
}
.upload-drop.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.hidden-input {
  display: none;
}
.icon {
  font-size: 32px;
}
.text {
  text-align: center;
}
.main {
  margin: 0;
  color: var(--vf-ink);
  font-size: 14px;
}
.hint {
  margin: 4px 0 0;
  color: var(--vf-ink-muted);
  font-size: 12px;
}
.link {
  color: var(--vf-accent);
}
</style>
