/**
 * Permission-aware UI helpers (B端-前端权限联动).
 *
 * Usage in SFCs:
 *   const { can } = usePermissions()
 *   <el-button v-if="can('task.write')" ...>上传</el-button>
 *
 * Or as a directive:
 *   <el-button v-perm="'task.write'">上传</el-button>
 */
import { computed } from 'vue'

import { usePermissionStore } from '@/stores/permission'

export function usePermissions() {
  const store = usePermissionStore()
  return {
    can: store.can,
    canAny: store.canAny,
    canAll: store.canAll,
    isAdmin: computed(() => store.isAdmin),
    loaded: computed(() => store.loaded),
    load: store.load,
  }
}

/**
 * Directive: v-perm="'task.write'" (renders only when permitted).
 * v-perm="{ code: 'task.write', mode: 'disable' }" — keeps the node but
 * sets `disabled` when the code is missing.
 */
export const vPerm = {
  mounted(el: HTMLElement, binding: { value: string | { code: string; mode?: 'hide' | 'disable' } }) {
    apply(el, binding.value)
  },
  updated(el: HTMLElement, binding: { value: string | { code: string; mode?: 'hide' | 'disable' } }) {
    apply(el, binding.value)
  },
}

function apply(el: HTMLElement, value: string | { code: string; mode?: 'hide' | 'disable' }): void {
  const store = usePermissionStore()
  const code = typeof value === 'string' ? value : value.code
  const mode = typeof value === 'string' ? 'hide' : (value.mode ?? 'hide')
  const ok = store.can(code)
  if (mode === 'hide') {
    el.style.display = ok ? '' : 'none'
  } else {
    if (!ok) {
      el.setAttribute('disabled', 'true')
      el.classList.add('is-disabled')
    } else {
      el.removeAttribute('disabled')
      el.classList.remove('is-disabled')
    }
  }
}
