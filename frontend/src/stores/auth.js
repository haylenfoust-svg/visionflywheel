import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { login as apiLogin, me as apiMe } from '@/api/auth';
export const useAuthStore = defineStore('auth', () => {
    const token = ref(localStorage.getItem('vf_token'));
    const user = ref(JSON.parse(localStorage.getItem('vf_user') ?? 'null'));
    const isLoggedIn = computed(() => Boolean(token.value));
    const isAdmin = computed(() => user.value?.role === 'admin');
    async function login(username, password) {
        const data = await apiLogin(username, password);
        token.value = data.access_token;
        user.value = data.user;
        localStorage.setItem('vf_token', data.access_token);
        localStorage.setItem('vf_user', JSON.stringify(data.user));
    }
    async function fetchMe() {
        if (!token.value)
            return;
        user.value = await apiMe();
        localStorage.setItem('vf_user', JSON.stringify(user.value));
    }
    function logout() {
        token.value = null;
        user.value = null;
        localStorage.removeItem('vf_token');
        localStorage.removeItem('vf_user');
    }
    return { token, user, isLoggedIn, isAdmin, login, fetchMe, logout };
});
