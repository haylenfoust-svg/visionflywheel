<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { usePermissionStore } from '@/stores/permission'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const perm = usePermissionStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const mounted = ref(false)

const canSubmit = computed(() => form.username.trim().length > 0 && form.password.length > 0)

onMounted(() => {
  requestAnimationFrame(() => (mounted.value = true))
})

async function onSubmit() {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    await perm.load(true)  // load the RBAC permission set alongside the token
    ElMessage.success('登录成功，正在跳转…')
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
  <div class="login" :class="{ 'is-mounted': mounted }">
    <!-- 动效背景：渐变网格 -->
    <div class="login__bg" aria-hidden="true">
      <div class="bg-orb bg-orb--1"></div>
      <div class="bg-orb bg-orb--2"></div>
      <div class="bg-orb bg-orb--3"></div>
      <div class="bg-grid"></div>
    </div>

    <!-- 左侧品牌介绍 -->
    <aside class="login__brand">
      <div class="brand-mark">
        <svg viewBox="0 0 24 24" class="brand-mark__logo" aria-hidden="true">
          <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="1.6" />
          <circle cx="12" cy="12" r="3.2" fill="currentColor" />
          <path
            d="M12 2v3.4M12 18.6V22M2 12h3.4M18.6 12H22"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          />
          <path
            d="M5.6 5.6l2.4 2.4M16 16l2.4 2.4M18.4 5.6L16 8M8 16l-2.4 2.4"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
          />
        </svg>
      </div>
      <h1 class="brand-title">视觉飞轮</h1>
      <p class="brand-subtitle">VisionFlywheel</p>
      <p class="brand-tagline">
        上传即识别 · 识别即可视化<br />
        看得不对就改 · 改完即训练
      </p>

      <ul class="feature-list">
        <li><span class="feature-icon">◎</span> YOLO 单阶段检测 · 实时画框</li>
        <li><span class="feature-icon">✎</span> Canvas 五种校正动作 · 拖拽即改</li>
        <li><span class="feature-icon">◈</span> 一键导出标准 YOLO 训练集</li>
        <li><span class="feature-icon">❖</span> 权重热切换 · 无需重启服务</li>
        <li><span class="feature-icon">✦</span> 智能分析 · 问答即数据</li>
      </ul>
    </aside>

    <!-- 右侧登录表单 -->
    <main class="login__main">
      <div class="login__card">
        <div class="card-header">
          <h2>登录</h2>
          <p>使用你的账号继续访问</p>
        </div>

        <form class="login-form" @submit.prevent="onSubmit">
          <div class="field">
            <label class="field-label" for="username">用户名</label>
            <div class="input-wrap">
              <span class="input-icon">👤</span>
              <input
                id="username"
                v-model="form.username"
                type="text"
                class="input"
                placeholder="请输入用户名"
                autocomplete="username"
                autofocus
              />
            </div>
          </div>

          <div class="field">
            <label class="field-label" for="password">密码</label>
            <div class="input-wrap">
              <span class="input-icon">🔒</span>
              <input
                id="password"
                v-model="form.password"
                type="password"
                class="input"
                placeholder="请输入密码"
                autocomplete="current-password"
                @keyup.enter="onSubmit"
              />
            </div>
          </div>

          <button
            type="submit"
            class="submit-btn"
            :class="{ 'is-loading': loading, 'is-active': canSubmit }"
            :disabled="!canSubmit || loading"
          >
            <span v-if="loading" class="spinner" aria-hidden="true"></span>
            <span v-else>登录</span>
            <span class="submit-btn__arrow" aria-hidden="true">→</span>
          </button>
        </form>

        <div class="card-footer">
          <p class="hint">
            首次使用？运行
            <code class="mono">python -m app.seed</code>
            创建管理员
          </p>
          <p class="hint hint--warn">
            默认密码 <code class="mono">admin123</code>，生产环境务必修改
          </p>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1fr 480px;
  background: var(--bg-app);
  position: relative;
  overflow: hidden;
}

/* 动效背景 */
.login__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.bg-orb {
  position: absolute;
  border-radius: var(--r-full);
  filter: blur(80px);
  opacity: 0.55;
  animation: orb-float 20s var(--ease-standard) infinite;
}
.bg-orb--1 {
  width: 480px; height: 480px;
  background: radial-gradient(circle, var(--c-primary-200), transparent 70%);
  top: -120px; left: -120px;
}
.bg-orb--2 {
  width: 380px; height: 380px;
  background: radial-gradient(circle, var(--c-primary-100), transparent 70%);
  bottom: -80px; right: 10%;
  animation-delay: -7s;
}
.bg-orb--3 {
  width: 280px; height: 280px;
  background: radial-gradient(circle, var(--c-info-50), transparent 70%);
  top: 30%; right: 30%;
  animation-delay: -14s;
}
@keyframes orb-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.05); }
  66% { transform: translate(-20px, 20px) scale(0.95); }
}
.bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, var(--c-neutral-200) 1px, transparent 1px),
    linear-gradient(to bottom, var(--c-neutral-200) 1px, transparent 1px);
  background-size: 48px 48px;
  opacity: 0.3;
  mask-image: radial-gradient(ellipse at 30% 50%, black 0%, transparent 75%);
}

/* 品牌介绍 */
.login__brand {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: var(--sp-16) var(--sp-12);
  animation: slide-in-right var(--t-slower) var(--ease-decelerate);
}
.brand-mark {
  width: 64px; height: 64px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--c-primary-500), var(--c-primary-700));
  color: white;
  border-radius: var(--r-xl);
  margin-bottom: var(--sp-5);
  box-shadow: var(--shadow-lg);
  transition: transform var(--t-slow) var(--ease-standard);
}
.brand-mark:hover {
  transform: rotate(15deg) scale(1.05);
}
.brand-mark__logo {
  width: 36px; height: 36px;
}
.brand-title {
  font-size: var(--fs-4xl);
  font-weight: var(--fw-bold);
  letter-spacing: -0.03em;
  background: linear-gradient(135deg, var(--c-primary-700), var(--c-primary-500));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.brand-subtitle {
  font-size: var(--fs-md);
  color: var(--text-tertiary);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  margin-bottom: var(--sp-6);
}
.brand-tagline {
  font-size: var(--fs-lg);
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: var(--sp-8);
}
.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.feature-list li {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  font-size: var(--fs-md);
  color: var(--text-primary);
  transition: all var(--t-fast) var(--ease-standard);
}
.feature-list li:hover {
  border-color: var(--border-accent);
  transform: translateX(4px);
}
.feature-icon {
  color: var(--text-accent);
  font-size: var(--fs-md);
}

/* 登录卡 */
.login__main {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8);
}
.login__card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-xl);
  padding: var(--sp-8);
  box-shadow: var(--shadow-lg);
  animation: slide-up var(--t-slower) var(--ease-decelerate);
}
.card-header {
  margin-bottom: var(--sp-6);
}
.card-header h2 {
  font-size: var(--fs-2xl);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.015em;
}
.card-header p {
  margin-top: var(--sp-1);
  color: var(--text-secondary);
  font-size: var(--fs-md);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.field-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-medium);
  color: var(--text-secondary);
}
.input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.input-icon {
  position: absolute;
  left: var(--sp-3);
  color: var(--text-tertiary);
  font-size: var(--fs-md);
  transition: all var(--t-fast) var(--ease-standard);
  pointer-events: none;
}
.input {
  width: 100%;
  padding: var(--sp-3) var(--sp-3) var(--sp-3) 40px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  font-size: var(--fs-md);
  color: var(--text-primary);
  transition: all var(--t-fast) var(--ease-standard);
}
.input::placeholder {
  color: var(--text-disabled);
}
.input:hover {
  border-color: var(--border-strong);
  background: var(--bg-surface);
}
.input:focus {
  outline: none;
  border-color: var(--border-focus);
  background: var(--bg-surface);
  box-shadow: var(--shadow-focus);
}
.input:focus + .input-icon,
.input:focus ~ .input-icon {
  color: var(--text-accent);
}

.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  width: 100%;
  padding: var(--sp-3) var(--sp-4);
  margin-top: var(--sp-2);
  background: var(--c-neutral-300);
  color: var(--c-neutral-500);
  border: none;
  border-radius: var(--r-md);
  font-size: var(--fs-md);
  font-weight: var(--fw-medium);
  cursor: not-allowed;
  transition: all var(--t-fast) var(--ease-standard);
  overflow: hidden;
  position: relative;
}
.submit-btn.is-active {
  background: linear-gradient(135deg, var(--c-primary-600), var(--c-primary-700));
  color: white;
  cursor: pointer;
}
.submit-btn.is-active:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 16px -6px rgb(var(--c-primary-600) / 0.4);
}
.submit-btn.is-active:active {
  transform: translateY(0);
}
.submit-btn__arrow {
  transition: transform var(--t-fast) var(--ease-standard);
}
.submit-btn.is-active:hover .submit-btn__arrow {
  transform: translateX(3px);
}

.spinner {
  width: 16px; height: 16px;
  border: 2px solid var(--c-neutral-300);
  border-top-color: white;
  border-radius: var(--r-full);
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.card-footer {
  margin-top: var(--sp-6);
  padding-top: var(--sp-4);
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.hint {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}
.hint--warn {
  color: var(--c-warning-600);
}
.hint code {
  padding: 1px var(--sp-2);
  background: var(--bg-subtle);
  border-radius: var(--r-xs);
  font-family: var(--font-mono);
  font-size: 0.92em;
}

/* 响应式 */
@media (max-width: 960px) {
  .login {
    grid-template-columns: 1fr;
  }
  .login__brand {
    display: none;
  }
}

/* 入场动效 */
.is-mounted .brand-mark { animation: scale-in var(--t-slower) var(--ease-decelerate); }
.is-mounted .brand-title { animation: slide-up var(--t-slower) var(--ease-decelerate) 80ms both; }
.is-mounted .brand-tagline { animation: slide-up var(--t-slower) var(--ease-decelerate) 160ms both; }
.is-mounted .feature-list li { animation: slide-in-right var(--t-slow) var(--ease-decelerate) both; }
.is-mounted .feature-list li:nth-child(1) { animation-delay: 200ms; }
.is-mounted .feature-list li:nth-child(2) { animation-delay: 280ms; }
.is-mounted .feature-list li:nth-child(3) { animation-delay: 360ms; }
.is-mounted .feature-list li:nth-child(4) { animation-delay: 440ms; }
.is-mounted .feature-list li:nth-child(5) { animation-delay: 520ms; }
</style>
