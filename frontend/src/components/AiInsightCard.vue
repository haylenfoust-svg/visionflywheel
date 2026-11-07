<script setup lang="ts">
import { computed } from 'vue'

/**
 * AiInsightCard — AI result card with confidence range + textual rationale.
 * Pattern borrowed from the campus-marketplace article's "AI 估价卡".
 *
 * Shows:
 *   - headline metric (e.g. "建议价 / 识别准确率")
 *   - confidence range (min / suggested / max) as a horizontal bar
 *   - confidence percentage with ring
 *   - textual rationale ("依据")
 *   - source badges (model / rules / knowledge)
 */
const props = withDefaults(
  defineProps<{
    title?: string
    headline: string
    headlineSub?: string
    confidence?: number | null
    range?: { min: number; max: number; suggested: number } | null
    rationale?: string
    sources?: Array<{ label: string; type?: 'model' | 'rule' | 'kb' }>
    tone?: 'primary' | 'success' | 'warning' | 'danger'
  }>(),
  {
    title: 'AI 智能分析',
    headlineSub: '',
    confidence: null,
    range: null,
    rationale: '',
    sources: () => [],
    tone: 'primary',
  },
)

const confPct = computed(() => {
  if (props.confidence == null) return null
  return Math.round(Math.max(0, Math.min(1, props.confidence)) * 100)
})

const rangeSpan = computed(() => {
  if (!props.range) return 0
  return Math.max(0, props.range.max - props.range.min)
})

const suggestedOffset = computed(() => {
  if (!props.range || rangeSpan.value === 0) return 50
  return ((props.range.suggested - props.range.min) / rangeSpan.value) * 100
})

const confTone = computed(() => {
  const v = confPct.value
  if (v == null) return 'neutral'
  if (v >= 75) return 'high'
  if (v >= 45) return 'mid'
  return 'low'
})
</script>

<template>
  <section class="ai-card" :class="`tone-${tone}`">
    <header class="ai-card__head">
      <div class="ai-card__title">
        <span class="ai-badge">AI</span>
        <span class="title">{{ title }}</span>
      </div>
      <slot name="actions" />
    </header>

    <div class="ai-card__body">
      <!-- headline -->
      <div class="ai-card__headline">
        <div class="headline-value num">{{ headline }}</div>
        <div v-if="headlineSub" class="headline-sub">{{ headlineSub }}</div>
      </div>

      <!-- confidence ring + range -->
      <div v-if="confPct != null || range" class="ai-card__metrics">
        <div v-if="confPct != null" class="conf-ring" :class="confTone">
          <svg viewBox="0 0 36 36" class="conf-ring__svg">
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--bg-subtle)" stroke-width="3" />
            <circle
              cx="18"
              cy="18"
              r="15.5"
              fill="none"
              :stroke="confTone === 'high' ? 'var(--c-success-500)' : confTone === 'mid' ? 'var(--c-warning-500)' : 'var(--c-danger-500)'"
              stroke-width="3"
              stroke-linecap="round"
              :stroke-dasharray="`${(confPct / 100) * 97.4} 97.4`"
              transform="rotate(-90 18 18)"
            />
          </svg>
          <div class="conf-ring__label">
            <div class="num">{{ confPct }}%</div>
            <div class="ring-sub">置信度</div>
          </div>
        </div>

        <div v-if="range" class="range-bar">
          <div class="range-bar__labels">
            <span class="num">{{ range.min.toLocaleString() }}</span>
            <span class="num suggested">{{ range.suggested.toLocaleString() }}</span>
            <span class="num">{{ range.max.toLocaleString() }}</span>
          </div>
          <div class="range-bar__track">
            <div class="range-bar__span" />
            <div class="range-bar__marker" :style="{ left: `${suggestedOffset}%` }">
              <div class="marker-label">建议</div>
            </div>
          </div>
        </div>
      </div>

      <!-- rationale -->
      <p v-if="rationale" class="ai-card__rationale">
        <span class="label">依据</span>
        {{ rationale }}
      </p>

      <!-- sources -->
      <div v-if="sources.length" class="ai-card__sources">
        <span class="label">来源</span>
        <span v-for="s in sources" :key="s.label" class="src-chip" :class="`src-${s.type ?? 'model'}`">
          {{ s.label }}
        </span>
      </div>

      <slot />
    </div>
  </section>
</template>

<style scoped>
.ai-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--r-lg);
  overflow: hidden;
  transition: border-color var(--t-fast) var(--ease-standard);
}
.ai-card.tone-primary { border-left: 3px solid var(--c-primary-500); }
.ai-card.tone-success { border-left: 3px solid var(--c-success-500); }
.ai-card.tone-warning { border-left: 3px solid var(--c-warning-500); }
.ai-card.tone-danger  { border-left: 3px solid var(--c-danger-500); }

.ai-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-subtle);
}
.ai-card__title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.ai-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: linear-gradient(135deg, var(--c-primary-500), var(--c-primary-700));
  color: white;
  font-size: 10px;
  font-weight: var(--fw-bold);
  letter-spacing: 0.05em;
  border-radius: var(--r-full);
}
.title {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--text-secondary);
}

.ai-card__body {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.ai-card__headline .headline-value {
  font-size: var(--fs-3xl);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.ai-card__headline .headline-sub {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-top: 2px;
}

.ai-card__metrics {
  display: flex;
  gap: var(--sp-6);
  align-items: center;
}
.conf-ring {
  position: relative;
  width: 84px;
  height: 84px;
  flex-shrink: 0;
}
.conf-ring__svg {
  width: 100%;
  height: 100%;
}
.conf-ring__label {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.conf-ring__label .num {
  font-size: var(--fs-xl);
  font-weight: var(--fw-semibold);
  line-height: 1;
}
.conf-ring__label .ring-sub {
  font-size: 10px;
  color: var(--text-tertiary);
}

.range-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.range-bar__labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.range-bar__labels .suggested {
  color: var(--c-primary-600);
  font-weight: var(--fw-semibold);
}
.range-bar__track {
  position: relative;
  height: 8px;
  background: var(--bg-subtle);
  border-radius: var(--r-full);
}
.range-bar__span {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, var(--c-primary-200), var(--c-primary-400));
  border-radius: var(--r-full);
}
.range-bar__marker {
  position: absolute;
  top: -4px;
  width: 2px;
  height: 16px;
  background: var(--c-primary-700);
  border-radius: 1px;
  transform: translateX(-1px);
}
.marker-label {
  position: absolute;
  top: -16px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--c-primary-700);
  font-weight: var(--fw-semibold);
  white-space: nowrap;
}

.ai-card__rationale {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.6;
  padding: var(--sp-2) var(--sp-3);
  background: var(--bg-subtle);
  border-radius: var(--r-sm);
}
.ai-card__rationale .label,
.ai-card__sources .label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-right: var(--sp-1);
}

.ai-card__sources {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.src-chip {
  padding: 2px 8px;
  font-size: var(--fs-xs);
  border-radius: var(--r-full);
}
.src-model { color: var(--c-primary-700); background: var(--c-primary-50); }
.src-rule  { color: var(--c-warning-600); background: var(--c-warning-50); }
.src-kb    { color: var(--c-success-600); background: var(--c-success-50); }
</style>
