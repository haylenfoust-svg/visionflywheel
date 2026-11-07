<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const collapsed = ref(false)
const pageTitle = computed(() => (route.meta.title as string) ?? '控制台')

const displayName = computed(() => auth.user?.display_name || auth.user?.username || '')
const initials = computed(() => (displayName.value[0] ?? '?').toUpperCase())
const roleLabel = computed(() => (auth.isAdmin ? '管理员' : '操作员'))

const navItems = computed(() => {
  const base = [
    { path: '/dashboard', icon: '◎', label: '控制台' },
    { path: '/detect', icon: '◉', label: '识别' },
    { path: '/annotate', icon: '✎', label: '校正工作台' },
    { path: '/dataset', icon: '◈', label: '数据与权重' },
    { path: '/chat', icon: '✦', label: '智能分析' },
  ]
  if (auth.isAdmin) {
    base.push({ path: '/admin', icon: '⚙', label: '系统管理' })
    base.push({ path: '/rbac', icon: '🔑', label: '身份与权限' })
  }
  return base
})

function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + '/')
}

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.replace('/login')
  } else if (cmd === 'admin' && auth.isAdmin) {
    router.push('/admin')
  }
}
</script>

<template>
  <el-container class="layout" :class="{ 'is-collapsed': collapsed }">
    <!-- 侧栏 -->
    <el-aside :width="collapsed ? '64px' : '240px'" class="layout__aside">
      <div class="brand" @click="router.push('/dashboard')">
        <div class="brand__mark">
          <svg viewBox="0 0 24 24" class="brand__logo" aria-hidden="true">
            <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2" />
            <circle cx="12" cy="12" r="3" fill="currentColor" />
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </div>
        <transition name="fade">
          <div v-if="!collapsed" class="brand__text">
            <div class="brand__name">视觉飞轮</div>
            <div class="brand__sub">VisionFlywheel</div>
          </div>
        </transition>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav__item"
          :class="{ 'is-active': isActive(item.path) }"
        >
          <span class="nav__icon">{{ item.icon }}</span>
          <transition name="fade">
            <span v-if="!collapsed" class="nav__label">{{ item.label }}</span>
          </transition>
          <span v-if="!collapsed && isActive(item.path)" class="nav__indicator" aria-hidden="true" />
        </router-link>
      </nav>

      <div class="aside__footer">
        <button
          class="collapse-btn"
          :title="collapsed ? '展开侧栏' : '收起侧栏'"
          @click="collapsed = !collapsed"
        >
          <span class="collapse-btn__icon" :class="{ 'is-collapsed': collapsed }">‹</span>
          <transition name="fade">
            <span v-if="!collapsed" class="collapse-btn__label">收起侧栏</span>
          </transition>
        </button>
      </div>
    </el-aside>

    <!-- 主区 -->
    <el-container class="layout__main">
      <el-header class="layout__header" height="56px">
        <div class="header__left">
          <h2 class="header__title">{{ pageTitle }}</h2>
        </div>

        <div class="header__right">
          <!-- 通知铃 -->
          <el-tooltip content="通知" placement="bottom">
            <button class="icon-btn" aria-label="通知">
              <svg viewBox="0 0 24 24" class="icon-btn__svg" aria-hidden="true">
                <path
                  d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </el-tooltip>

          <!-- 用户下拉 -->
          <el-dropdown trigger="click" @command="handleCommand">
            <button class="user-menu">
              <span class="user-menu__avatar">{{ initials }}</span>
              <span v-if="!collapsed" class="user-menu__info">
                <span class="user-menu__name">{{ displayName }}</span>
                <span class="user-menu__role">{{ roleLabel }}</span>
              </span>
              <svg viewBox="0 0 24 24" class="user-menu__chev" aria-hidden="true">
                <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
              </svg>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <div class="dropdown-user">
                    <div class="dropdown-user__name">{{ displayName }}</div>
                    <div class="dropdown-user__email">{{ auth.user?.username }}</div>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item v-if="auth.isAdmin" divided command="admin">
                  ⚙ 系统管理
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  ⏻ 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout__content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  background: var(--bg-app);
}
.layout__aside {
  background: var(--bg-surface);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  transition: width var(--t-base) var(--ease-standard);
  overflow: hidden;
}

/* 品牌 */
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-5) var(--sp-4);
  cursor: pointer;
  border-bottom: 1px solid var(--border-default);
  user-select: none;
  min-height: 56px;
}
.brand__mark {
  flex-shrink: 0;
  width: 32px; height: 32px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--c-primary-500), var(--c-primary-700));
  color: white;
  border-radius: var(--r-md);
  transition: transform var(--t-fast) var(--ease-standard);
}
.brand:hover .brand__mark { transform: rotate(15deg) scale(1.05); }
.brand__logo { width: 20px; height: 20px; }
.brand__text { min-width: 0; overflow: hidden; }
.brand__name {
  font-size: var(--fs-md);
  font-weight: var(--fw-semibold);
  color: var(--text-primary);
  letter-spacing: -0.01em;
  white-space: nowrap;
}
.brand__sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  letter-spacing: 0.03em;
  text-transform: uppercase;
  white-space: nowrap;
}

/* 导航 */
.nav {
  flex: 1;
  padding: var(--sp-3) var(--sp-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}
.nav__item {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
  color: var(--text-secondary);
  font-size: var(--fs-md);
  transition:
    background var(--t-fast) var(--ease-standard),
    color var(--t-fast) var(--ease-standard),
    transform var(--t-fast) var(--ease-standard);
  text-decoration: none;
}
.nav__item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  transform: translateX(2px);
}
.nav__item.is-active {
  background: var(--c-primary-50);
  color: var(--c-primary-700);
  font-weight: var(--fw-medium);
}
.nav__item.is-active .nav__icon {
  background: var(--c-primary-600);
  color: white;
  transform: scale(1.05);
}
.nav__indicator {
  position: absolute;
  right: var(--sp-2);
  width: 4px; height: 4px;
  border-radius: var(--r-full);
  background: var(--c-primary-600);
}
.nav__icon {
  flex-shrink: 0;
  width: 28px; height: 28px;
  display: grid;
  place-items: center;
  font-size: var(--fs-md);
  border-radius: var(--r-sm);
  transition: all var(--t-fast) var(--ease-standard);
}
.nav__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.aside__footer {
  padding: var(--sp-3);
  border-top: 1px solid var(--border-default);
}
.collapse-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: var(--fs-sm);
  cursor: pointer;
  border-radius: var(--r-md);
  transition: all var(--t-fast) var(--ease-standard);
}
.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.collapse-btn__icon {
  font-size: 18px;
  transition: transform var(--t-base) var(--ease-standard);
}
.collapse-btn__icon.is-collapsed { transform: rotate(180deg); }

/* 头部 */
.layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-6);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-default);
  z-index: var(--z-sticky);
}
.header__title {
  font-size: var(--fs-lg);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.01em;
}
.header__right {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.icon-btn {
  width: 36px; height: 36px;
  display: grid;
  place-items: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.icon-btn__svg { width: 18px; height: 18px; }

.user-menu {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-md);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.user-menu:hover {
  background: var(--bg-hover);
  border-color: var(--border-default);
}
.user-menu__avatar {
  width: 32px; height: 32px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--c-primary-400), var(--c-primary-600));
  color: white;
  border-radius: var(--r-full);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}
.user-menu__info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
}
.user-menu__name {
  font-size: var(--fs-base);
  font-weight: var(--fw-medium);
  color: var(--text-primary);
}
.user-menu__role {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.user-menu__chev {
  width: 14px; height: 14px;
  color: var(--text-tertiary);
}

.dropdown-user__name {
  font-weight: var(--fw-medium);
  color: var(--text-primary);
}
.dropdown-user__email {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

/* 内容 */
.layout__content {
  padding: 0;
  overflow-x: hidden;
}

/* 转场 */
.fade-enter-active, .fade-leave-active {
  transition: opacity var(--t-fast) var(--ease-standard);
}
.fade-enter-from, .fade-leave-to { opacity: 0; }

.page-enter-active, .page-leave-active {
  transition:
    opacity var(--t-base) var(--ease-standard),
    transform var(--t-base) var(--ease-standard);
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 响应式 */
@media (max-width: 900px) {
  .layout__aside {
    position: fixed;
    z-index: var(--z-drawer);
    height: 100vh;
  }
}
</style>
