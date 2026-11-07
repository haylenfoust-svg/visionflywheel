import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
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
        meta: { title: '控制台' },
      },
      {
        path: 'detect',
        name: 'detect',
        component: () => import('@/views/Detect.vue'),
        meta: { title: '识别' },
      },
      {
        path: 'annotate',
        name: 'annotate',
        component: () => import('@/views/Annotate.vue'),
        meta: { title: '校正工作台' },
      },
      {
        path: 'dataset',
        name: 'dataset',
        component: () => import('@/views/Dataset.vue'),
        meta: { title: '数据与权重' },
      },
      {
        path: 'chat',
        name: 'chat',
        component: () => import('@/views/Chat.vue'),
        meta: { title: '智能分析' },
      },
      {
        path: 'admin',
        name: 'admin',
        component: () => import('@/views/Admin.vue'),
        meta: { title: '系统管理', adminOnly: true },
      },
      {
        path: 'rbac',
        name: 'rbac',
        component: () => import('@/views/Rbac.vue'),
        meta: { title: '身份与权限', adminOnly: true },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    return true
  }
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.adminOnly && !auth.isAdmin) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
