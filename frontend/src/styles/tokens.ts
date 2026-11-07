/**
 * Design tokens — JS-side access (P3.2 / tokens-first).
 *
 * Charts and Canvas code can't use CSS vars directly in all contexts,
 * so this module exposes the same role-based palette as `design-system.scss`.
 *
 * RULES (from UI/UX Pro Max "Tokens before components"):
 *  1. Never hardcode hex/rgb in components — call `token('chart-primary')`.
 *  2. Name tokens by ROLE, never by value.
 *  3. Missing token? STOP and propose a new one. Do not improvise.
 */

// Role → hex. Keep in sync with design-system.scss.
export const tokens = {
  // primary palette (indigo)
  primary: '#6366f1',
  primaryLight: '#818cf8',
  primaryDark: '#4f46e5',

  // semantic
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#3b82f6',

  // neutrals
  neutral0: '#ffffff',
  neutral50: '#fafbfc',
  neutral100: '#f4f6f8',
  neutral200: '#e8ecf0',
  neutral300: '#d5dce3',
  neutral400: '#a8b4c0',
  neutral500: '#7d8b99',
  neutral600: '#5a6874',
  neutral700: '#3d4750',
  neutral800: '#242c34',
  neutral900: '#13181d',

  // chart roles
  'chart-primary': '#6366f1',
  'chart-success': '#10b981',
  'chart-warning': '#f59e0b',
  'chart-danger': '#ef4444',
  'chart-info': '#3b82f6',
  'chart-accent': '#818cf8',
  'chart-fill': 'rgba(99, 102, 241, 0.12)',
  'chart-fill-alt': 'rgba(16, 185, 129, 0.12)',
  'chart-fill-warn': 'rgba(245, 158, 11, 0.12)',
  'chart-fill-danger': 'rgba(239, 68, 68, 0.12)',

  // canvas roles
  'canvas-stroke': '#6366f1',
  'canvas-stroke-alt': '#ef4444',
  'canvas-stroke-ok': '#10b981',
  'canvas-stroke-warn': '#f59e0b',
  'canvas-fill': '#ffffff',
  'canvas-draft': '#6366f1',
  'canvas-draft-fill': 'rgba(25, 118, 210, 0.12)',
  'canvas-handle': '#ffffff',
} as const

export type TokenName = keyof typeof tokens

/** Dark-mode overrides — keep in sync with design-system.scss [data-theme='dark']. */
const darkTokens: Partial<Record<TokenName, string>> = {
  neutral0: '#161b22',
  neutral50: '#0e1117',
  neutral100: '#1c2330',
  neutral200: '#2a3240',
  neutral300: '#3d4756',
  neutral400: '#4a5563',
  neutral500: '#6e7b8a',
  neutral600: '#9aa7b4',
  neutral700: '#c5ced8',
  neutral800: '#dfe5ec',
  neutral900: '#e6edf3',

  'chart-fill': 'rgba(99, 102, 241, 0.22)',
  'chart-fill-alt': 'rgba(16, 185, 129, 0.22)',
  'chart-fill-warn': 'rgba(245, 158, 11, 0.22)',
  'chart-fill-danger': 'rgba(239, 68, 68, 0.22)',

  'canvas-fill': '#161b22',
  'canvas-handle': '#2a3242',
}

export function isDark(): boolean {
  if (typeof document === 'undefined') return false
  return document.documentElement.getAttribute('data-theme') === 'dark'
}

export function token(name: TokenName): string {
  if (isDark() && darkTokens[name] !== undefined) return darkTokens[name] as string
  return tokens[name]
}

/**
 * Role → chart color. Charts receive a `color` prop as either:
 *  - a role name ('primary' | 'success' | ...), or
 *  - a raw CSS color (for one-off cases).
 */
export function chartColor(role: string): string {
  const map: Record<string, string> = {
    primary: tokens.primary,
    success: tokens.success,
    warning: tokens.warning,
    danger: tokens.danger,
    info: tokens.info,
    accent: tokens['chart-accent'],
  }
  return map[role] ?? role
}

export function chartFill(role: string): string {
  const map: Record<string, string> = {
    primary: token('chart-fill'),
    success: token('chart-fill-alt'),
    warning: token('chart-fill-warn'),
    danger: token('chart-fill-danger'),
  }
  return map[role] ?? token('chart-fill')
}

/**
 * Canvas drawing colors — used by ImageAnnotator.
 */
export const canvas = {
  get stroke() { return token('canvas-stroke') },
  get strokeAlt() { return token('canvas-stroke-alt') },
  get strokeOk() { return token('canvas-stroke-ok') },
  get strokeWarn() { return token('canvas-stroke-warn') },
  get fill() { return token('canvas-fill') },
  get draft() { return token('canvas-draft') },
  get draftFill() { return token('canvas-draft-fill') },
  get handle() { return token('canvas-handle') },
}

/**
 * Status → color role (used by DetectionTable, Dashboard, etc.).
 */
export function statusColor(status: string): string {
  switch (status) {
    case 'pending':
      return token('warning')
    case 'corrected':
    case 'done':
      return token('success')
    case 'rejected':
    case 'failed':
      return token('danger')
    default:
      return token('neutral500')
  }
}
