<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const displayName = computed(() => auth.user?.display_name || auth.user?.username || '')
const roleLabel = computed(() => (auth.isAdmin ? '管理员' : '操作员'))

function onLogout() {
  auth.logout()
  router.replace('/login')
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <el-menu router :default-active="$route.path" class="menu">
        <el-menu-item index="/dashboard">控制台</el-menu-item>
        <el-menu-item index="/detect">识别</el-menu-item>
        <el-menu-item index="/annotate">校正工作台</el-menu-item>
        <el-menu-item index="/dataset">数据与权重</el-menu-item>
        <el-menu-item index="/chat">智能分析</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin">系统管理</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="user">
          <span class="name">{{ displayName }}</span>
          <el-tag size="small" :type="auth.isAdmin ? 'warning' : 'info'">{{ roleLabel }}</el-tag>
        </div>
        <el-button text @click="onLogout">退出登录</el-button>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.aside {
  background: var(--vf-surface);
  border-right: 1px solid var(--vf-border);
}
.menu {
  border-right: none;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--vf-surface);
  border-bottom: 1px solid var(--vf-border);
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.name {
  font-weight: 500;
}
.main {
  padding: 0;
}
</style>
