/**
 * Theme — light / dark / system, persisted to localStorage.
 *
 * Sets `data-theme` (our CSS vars) and `.dark` class (Element Plus) on <html>.
 */
import { computed, readonly, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'vf-theme'

function getStored(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    /* private mode */
  }
  return 'system'
}

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolveMode(m: ThemeMode): 'light' | 'dark' {
  return m === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : m
}

function applyDom(resolved: 'light' | 'dark'): void {
  const html = document.documentElement
  html.setAttribute('data-theme', resolved)
  html.classList.toggle('dark', resolved === 'dark')
}

const mode = ref<ThemeMode>(getStored())
const resolved = computed(() => resolveMode(mode.value))

// apply immediately on module load (before first paint)
applyDom(resolveMode(mode.value))

// react to OS-level changes while in system mode
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (mode.value === 'system') applyDom(resolveMode('system'))
})

function setTheme(next: ThemeMode): void {
  mode.value = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* ignore */
  }
  applyDom(resolveMode(next))
}

function cycleTheme(): void {
  const order: ThemeMode[] = ['light', 'dark', 'system']
  const idx = order.indexOf(mode.value)
  setTheme(order[(idx + 1) % order.length])
}

export const THEME_LABELS: Record<ThemeMode, string> = {
  light: '浅色',
  dark: '深色',
  system: '跟随系统',
}

export function useTheme() {
  return {
    mode: readonly(mode),
    resolved,
    setTheme,
    cycleTheme,
  }
}
