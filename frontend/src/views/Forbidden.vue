<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const requiredPermission = computed(() => (route.meta.requiredPermission as string) ?? '')
const requiredAny = computed(() => (route.meta.requiredAny as string[]) ?? [])
const reason = computed(() => {
  if (requiredPermission.value) return `需要权限：${requiredPermission.value}`
  if (requiredAny.value.length) return `需要权限之一：${requiredAny.value.join(' / ')}`
  return '你的账号无权访问此页面'
})

function goHome() {
  router.replace('/dashboard')
}
</script>

<template>
  <div class="forbidden">
    <div class="forbidden__card">
      <div class="forbidden__code">403</div>
      <h1 class="forbidden__title">访问被拒绝</h1>
      <p class="forbidden__reason">{{ reason }}</p>
      <p class="forbidden__hint">
        当前账号：<strong>{{ auth.user?.username }}</strong>
        （{{ auth.isAdmin ? '管理员' : '操作员' }}）
      </p>
      <div class="forbidden__actions">
        <el-button type="primary" @click="goHome">返回控制台</el-button>
        <el-button @click="router.back()">返回上一页</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.forbidden {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-app);
  padding: var(--sp-6);
}
.forbidden__card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-xl);
  padding: var(--sp-12);
  text-align: center;
  max-width: 480px;
  animation: slide-up var(--t-slow) var(--ease-decelerate);
}
.forbidden__code {
  font-size: 80px;
  font-weight: var(--fw-bold);
  letter-spacing: -0.03em;
  background: linear-gradient(135deg, var(--c-danger-500), var(--c-warning-500));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1;
  margin-bottom: var(--sp-3);
}
.forbidden__title {
  font-size: var(--fs-2xl);
  font-weight: var(--fw-semibold);
  margin: 0 0 var(--sp-3);
}
.forbidden__reason {
  font-size: var(--fs-md);
  color: var(--text-secondary);
  margin: 0 0 var(--sp-3);
}
.forbidden__hint {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
  margin: 0 0 var(--sp-6);
}
.forbidden__actions {
  display: flex;
  gap: var(--sp-3);
  justify-content: center;
}
</style>
