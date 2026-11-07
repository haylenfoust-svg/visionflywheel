<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { health, systemInfo } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const info = ref<{ version: string; detector_mode: string; default_weight_id: number | null; enable_fallback_detector: boolean } | null>(null)
const healthStatus = ref<{ status: string; version: string; detector_mode: string; db: string } | null>(null)
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const [h, i] = await Promise.all([health(), systemInfo()])
    healthStatus.value = h
    info.value = i
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page dashboard">
    <h2>控制台</h2>
    <p class="lead">
      欢迎回来，<strong>{{ auth.user?.display_name || auth.user?.username }}</strong>
    </p>

    <div v-if="loading" class="loading">加载中…</div>

    <template v-else>
      <div class="grid">
        <div class="card stat">
          <div class="label">系统版本</div>
          <div class="value">{{ info?.version ?? '—' }}</div>
        </div>
        <div class="card stat">
          <div class="label">检测器</div>
          <div class="value">
            <el-tag :type="info?.detector_mode === 'yolo' ? 'success' : 'warning'">
              {{ info?.detector_mode ?? '—' }}
            </el-tag>
          </div>
        </div>
        <div class="card stat">
          <div class="label">默认权重</div>
          <div class="value">{{ info?.default_weight_id ?? '未设置' }}</div>
        </div>
        <div class="card stat">
          <div class="label">数据库</div>
          <div class="value">
            <el-tag :type="healthStatus?.db === 'ok' ? 'success' : 'danger'">
              {{ healthStatus?.db ?? '—' }}
            </el-tag>
          </div>
        </div>
      </div>

      <div class="card roadmap">
        <h3>下一步</h3>
        <ul>
          <li>✅ M1 骨架：登录、权限矩阵、配置中心</li>
          <li>⏭ M2 识别主链：上传 → YOLO 推理 → 落库 → 可视化</li>
          <li>⏭ M3 校正闭环：Canvas 五种校正动作</li>
          <li>⏭ M4 导出与回流：YOLO 训练集 + 增量训练 + 权重热切换</li>
          <li>⏭ M5 智能分析：LangGraph + RAG</li>
          <li>⏭ M6 加固交付：批量/视频 + 降级 + Docker</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.lead {
  color: var(--vf-ink-muted);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin: 16px 0;
}
.stat .label {
  color: var(--vf-ink-muted);
  font-size: 12px;
  margin-bottom: 8px;
}
.stat .value {
  font-size: 22px;
  font-weight: 600;
}
.roadmap ul {
  margin: 8px 0 0;
  padding-left: 18px;
  line-height: 1.9;
}
.loading {
  padding: 24px;
  color: var(--vf-ink-muted);
}
</style>
