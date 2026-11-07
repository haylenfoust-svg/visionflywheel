<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

const canSubmit = computed(() => form.username.trim().length > 0 && form.password.length > 0)

async function onSubmit() {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) ?? '/dashboard'
    router.replace(redirect)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="title">
        <div class="mark">◉</div>
        <h1>视觉飞轮</h1>
        <p class="sub">VisionFlywheel · 自进化图像识别闭环</p>
      </div>

      <el-form label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" autofocus />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            show-password
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit"
          :loading="loading"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          登录
        </el-button>
      </el-form>

      <p class="hint">首次使用？请运行 <code>python -m app.seed</code> 创建管理员。</p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--vf-accent-soft), var(--vf-bg));
  padding: 24px;
}
.login-card {
  width: 380px;
  background: var(--vf-surface);
  border-radius: var(--vf-radius-lg);
  border: 1px solid var(--vf-border);
  padding: 36px 32px;
}
.title {
  text-align: center;
  margin-bottom: 24px;
}
.mark {
  font-size: 28px;
  color: var(--vf-accent);
}
h1 {
  margin: 8px 0 4px;
  font-size: 22px;
  letter-spacing: 1px;
}
.sub {
  color: var(--vf-ink-muted);
  font-size: 12px;
  margin: 0;
}
.submit {
  width: 100%;
  margin-top: 8px;
}
.hint {
  margin-top: 18px;
  font-size: 12px;
  color: var(--vf-ink-muted);
  text-align: center;
}
.hint code {
  font-family: var(--vf-font-mono);
  background: var(--vf-bg);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
