import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { usePermissionStore } from '@/stores/permission'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/forbidden',
    name: 'forbidden',
    component: () => import('@/views/Forbidden.vue'),
    meta: { public: false },
  },
  {
    path: '/',
    name: 'layout',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '控制台', requiredAny: ['task.read', 'detection.read'] },
      },
      {
        path: 'detect',
        name: 'detect',
        component: () => import('@/views/Detect.vue'),
        meta: { title: '识别', requiredAny: ['task.read', 'task.write', 'detection.read'] },
      },
      {
        path: 'annotate',
        name: 'annotate',
        component: () => import('@/views/Annotate.vue'),
        meta: { title: '校正工作台', requiredAny: ['detection.read', 'detection.correct'] },
      },
      {
        path: 'dataset',
        name: 'dataset',
        component: () => import('@/views/Dataset.vue'),
        meta: { title: '数据与权重', requiredAny: ['dataset.read', 'weight.read', 'train.read'] },
      },
      {
        path: 'chat',
        name: 'chat',
        component: () => import('@/views/Chat.vue'),
        meta: { title: '智能分析', requiredAny: ['chat.use'] },
      },
      {
        path: 'admin',
        name: 'admin',
        component: () => import('@/views/Admin.vue'),
        meta: { title: '系统管理', adminOnly: true, requiredAny: ['system.admin', 'user.read', 'config.read', 'audit.read'] },
      },
      {
        path: 'rbac',
        name: 'rbac',
        component: () => import('@/views/Rbac.vue'),
        meta: { title: '身份与权限', adminOnly: true, requiredAny: ['system.admin', 'role.read', 'user.read'] },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const perm = usePermissionStore()

  // Public routes (login, etc.) pass through
  if (to.meta.public) return true

  // Must be logged in
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Ensure permission set is loaded (safe to call repeatedly)
  if (!perm.loaded) {
    await perm.load()
  }

  // Legacy admin-only flag
  if (to.meta.adminOnly && !auth.isAdmin && !perm.isAdmin) {
    return { name: 'forbidden', query: { from: to.fullPath } }
  }

  // Fine-grained permission check (B端-前端权限联动)
  const required = to.meta.requiredPermission as string | undefined
  const requiredAny = to.meta.requiredAny as string[] | undefined

  if (required && !perm.can(required)) {
    return {
      name: 'forbidden',
      query: { from: to.fullPath, code: required },
    }
  }
  if (requiredAny && requiredAny.length > 0 && !perm.canAny(...requiredAny)) {
    return {
      name: 'forbidden',
      query: { from: to.fullPath, code: requiredAny.join(',') },
    }
  }

  return true
})

export default router
