import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
const routes = [
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
        ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
];
const router = createRouter({
    history: createWebHistory(),
    routes,
});
router.beforeEach((to) => {
    const auth = useAuthStore();
    if (to.meta.public) {
        return true;
    }
    if (!auth.isLoggedIn) {
        return { name: 'login', query: { redirect: to.fullPath } };
    }
    return true;
});
export default router;
