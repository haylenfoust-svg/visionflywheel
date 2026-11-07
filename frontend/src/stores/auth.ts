import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { login as apiLogin, me as apiMe } from '@/api/auth'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('vf_token'))
  const user = ref<User | null>(JSON.parse(localStorage.getItem('vf_user') ?? 'null'))

  const isLoggedIn = computed(() => Boolean(token.value))
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username: string, password: string): Promise<void> {
    const data = await apiLogin(username, password)
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('vf_token', data.access_token)
    localStorage.setItem('vf_user', JSON.stringify(data.user))
  }

  async function fetchMe(): Promise<void> {
    if (!token.value) return
    user.value = await apiMe()
    localStorage.setItem('vf_user', JSON.stringify(user.value))
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('vf_token')
    localStorage.removeItem('vf_user')
  }

  return { token, user, isLoggedIn, isAdmin, login, fetchMe, logout }
})
