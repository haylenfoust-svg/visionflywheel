<script setup lang="ts">
import { computed } from 'vue'

import type { Detection } from '@/types/detection'

const props = defineProps<{
  detections: Detection[]
}>()

const emit = defineEmits<{
  (e: 'select', detection: Detection): void
}>()

const statusLabel: Record<string, string> = {
  pending: '待校正',
  corrected: '已校正',
  rejected: '已否决',
}

const statusType: Record<string, 'info' | 'success' | 'danger'> = {
  pending: 'info',
  corrected: 'success',
  rejected: 'danger',
}

const rows = computed(() => props.detections)

function displayName(d: Detection): string {
  return d.class_name_zh || d.class_name
}

function formatBox(d: Detection): string {
  const r = (n: number) => Math.round(n)
  return `${r(d.bbox.x1)}, ${r(d.bbox.y1)}, ${r(d.bbox.x2)}, ${r(d.bbox.y2)}`
}
</script>

<template>
  <el-table
    :data="rows"
    size="small"
    class="detection-table"
    @row-click="(row: Detection) => emit('select', row)"
  >
    <el-table-column prop="id" label="ID" width="70" />
    <el-table-column label="类别" min-width="120">
      <template #default="{ row }">
        <el-tag size="small" effect="plain">{{ displayName(row as Detection) }}</el-tag>
        <span v-if="(row as Detection).class_name_zh" class="sub">
          {{ (row as Detection).class_name }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="置信度" width="110" sortable>
      <template #default="{ row }">
        <span class="conf">{{ ((row as Detection).confidence * 100).toFixed(1) }}%</span>
      </template>
    </el-table-column>
    <el-table-column label="坐标 (x1,y1,x2,y2)" min-width="180">
      <template #default="{ row }">
        <code class="box">{{ formatBox(row as Detection) }}</code>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag size="small" :type="statusType[(row as Detection).status]">
          {{ statusLabel[(row as Detection).status] ?? (row as Detection).status }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="来源" width="80">
      <template #default="{ row }">
        <span class="sub">{{ (row as Detection).source === 'model' ? '模型' : '人工' }}</span>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty description="暂无检测结果" />
    </template>
  </el-table>
</template>

<style scoped>
.detection-table {
  width: 100%;
}
.sub {
  margin-left: 6px;
  color: var(--vf-ink-muted);
  font-size: 11px;
}
.conf {
  font-variant-numeric: tabular-nums;
}
.box {
  font-family: var(--vf-font-mono);
  font-size: 11px;
  background: var(--vf-bg);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
