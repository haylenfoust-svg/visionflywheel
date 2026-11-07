/**
 * Permission store (B端-前端权限联动).
 *
 * Fetches the caller's permission set from /api/rbac/my-permissions and
 * exposes a `can(code)` helper that views use to hide/disable actions.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { myPermissions } from '@/api/rbac'

export const usePermissionStore = defineStore('permission', () => {
  const codes = ref<Set<string>>(new Set())
  const isAdmin = ref(false)
  const loaded = ref(false)
  const loading = ref(false)

  const allCodes = computed(() => Array.from(codes.value))

  function can(code: string): boolean {
    if (isAdmin.value) return true
    return codes.value.has(code)
  }

  function canAny(...list: string[]): boolean {
    if (isAdmin.value) return true
    return list.some((c) => codes.value.has(c))
  }

  function canAll(...list: string[]): boolean {
    if (isAdmin.value) return true
    return list.every((c) => codes.value.has(c))
  }

  async function load(force = false): Promise<void> {
    if (loaded.value && !force) return
    loading.value = true
    try {
      const data = await myPermissions()
      codes.value = new Set(data.codes)
      isAdmin.value = data.is_admin
      loaded.value = true
    } catch (err) {
      // If we cannot load, fall back to permissive behavior so the UI
      // is not bricked by a transient backend error — the server still
      // enforces the permission gate.
      console.warn('permission load failed', err)
      codes.value = new Set()
      isAdmin.value = true
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    codes.value = new Set()
    isAdmin.value = false
    loaded.value = false
  }

  return { codes, isAdmin, loaded, loading, allCodes, can, canAny, canAll, load, reset }
})
