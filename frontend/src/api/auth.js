import { apiGet, apiPost, apiPut } from './http';
export async function login(username, password) {
    return apiPost('/api/auth/login', { username, password });
}
export async function me() {
    return apiGet('/api/auth/me');
}
export async function listUsers() {
    return apiGet('/api/auth/users');
}
export async function createUser(payload) {
    return apiPost('/api/auth/users', payload);
}
export async function updateUser(id, payload) {
    return apiPut(`/api/auth/users/${id}`, payload);
}
export async function systemInfo() {
    return apiGet('/api/system/info');
}
export async function health() {
    return apiGet('/api/system/health');
}
