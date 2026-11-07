import axios from 'axios';
const API_BASE = import.meta.env.VITE_API_BASE ?? '';
export const http = axios.create({
    baseURL: API_BASE,
    timeout: 30_000,
    headers: { 'Content-Type': 'application/json' },
});
http.interceptors.request.use((config) => {
    const token = localStorage.getItem('vf_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});
http.interceptors.response.use((response) => {
    const body = response.data;
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
        return Promise.reject(new Error(body.message || `error code ${body.code}`));
    }
    return response;
}, (error) => {
    const status = error.response?.status;
    const message = error.response?.data?.message ?? error.message;
    if (status === 401) {
        localStorage.removeItem('vf_token');
        localStorage.removeItem('vf_user');
        if (!window.location.pathname.startsWith('/login')) {
            window.location.href = '/login';
        }
    }
    return Promise.reject(new Error(message));
});
/** Convenience wrapper that unwraps `data` from the standard envelope. */
export async function apiGet(url, params) {
    const resp = await http.get(url, { params });
    return resp.data.data;
}
export async function apiPost(url, payload) {
    const resp = await http.post(url, payload);
    return resp.data.data;
}
export async function apiPut(url, payload) {
    const resp = await http.put(url, payload);
    return resp.data.data;
}
export async function apiDelete(url) {
    const resp = await http.delete(url);
    return resp.data.data;
}
