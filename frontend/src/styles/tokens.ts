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

export function token(name: TokenName): string {
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
    primary: tokens['chart-fill'],
    success: tokens['chart-fill-alt'],
    warning: tokens['chart-fill-warn'],
    danger: tokens['chart-fill-danger'],
  }
  return map[role] ?? tokens['chart-fill']
}

/**
 * Canvas drawing colors — used by ImageAnnotator.
 */
export const canvas = {
  stroke: tokens['canvas-stroke'],
  strokeAlt: tokens['canvas-stroke-alt'],
  strokeOk: tokens['canvas-stroke-ok'],
  strokeWarn: tokens['canvas-stroke-warn'],
  fill: tokens['canvas-fill'],
  draft: tokens['canvas-draft'],
  draftFill: tokens['canvas-draft-fill'],
  handle: tokens['canvas-handle'],
} as const

/**
 * Status → color role (used by DetectionTable, Dashboard, etc.).
 */
export function statusColor(status: string): string {
  switch (status) {
    case 'pending':
      return tokens.warning
    case 'corrected':
    case 'done':
      return tokens.success
    case 'rejected':
    case 'failed':
      return tokens.danger
    default:
      return tokens.neutral500
  }
}
