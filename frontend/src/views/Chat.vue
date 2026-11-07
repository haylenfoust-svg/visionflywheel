<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { addKnowledge, askChat, deleteKnowledge, listKnowledge } from '@/api/chat'
import type { ChatMessage, KnowledgeEntry } from '@/api/chat'
import AppCard from '@/components/AppCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'

const auth = useAuthStore()
const { can } = usePermissions()
const messages = ref<ChatMessage[]>([])
const input = ref('')
const loading = ref(false)
const knowledge = ref<KnowledgeEntry[]>([])
const listRef = ref<HTMLElement | null>(null)
const activeTab = ref<'chat' | 'knowledge'>('chat')

const SUGGESTIONS = [
  '今天识别了多少 defect？',
  '最常见的类别是什么？',
  '校正动作分布如何？',
  '今天做了哪些校正？',
  '系统有多少训练集？',
  '待处理工单有几条？',
]

const intentLabel: Record<string, string> = {
  count_detections: '检测统计',
  count_corrections: '校正统计',
  top_class: '类别分布',
  today_summary: '今日概览',
  dataset_info: '数据集',
  weight_info: '权重',
  ticket_info: '工单',
  help: '帮助',
  general: '一般',
}

async function send(text?: string) {
  const question = (text ?? input.value).trim()
  if (!question || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: question, ts: Date.now() })
  await scrollToBottom()
  loading.value = true
  try {
    const reply = await askChat(question)
    messages.value.push({
      role: 'assistant',
      content: reply.answer,
      sources: reply.sources,
      intent: reply.intent,
      checked: reply.is_hallucination_checked,
      ts: Date.now(),
    })
    await scrollToBottom()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '提问失败')
  } finally {
    loading.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function saveToKnowledge(msg: ChatMessage) {
  const question = messages.value.filter((m) => m.role === 'user').slice(-1)[0]?.content ?? ''
  if (!question) return
  try {
    await addKnowledge(question, msg.content)
    await refreshKnowledge()
    ElMessage.success('✦ 已存入知识库')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  }
}

async function refreshKnowledge() {
  try {
    knowledge.value = await listKnowledge()
  } catch {
    /* ignore */
  }
}

async function onDeleteKnowledge(k: KnowledgeEntry) {
  if (!auth.isAdmin) return
  try {
    await ElMessageBox.confirm(`删除知识条目「${k.question}」？`, '确认', { type: 'warning' })
    await deleteKnowledge(k.id)
    await refreshKnowledge()
    ElMessage.success('已删除')
  } catch {
    /* cancelled */
  }
}

function formatMessage(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
  return escaped
    .replace(/\n/g, '<br/>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

onMounted(() => {
  messages.value.push({
    role: 'assistant',
    content:
      '你好，我是 VisionFlywheel 的智能分析助手。\n\n' +
      '我可以基于真实识别数据回答问题——\n' +
      '· 识别了多少目标 / defect\n· 类别分布 · 校正动作\n· 今日概览\n· 数据集 / 权重 / 工单\n\n' +
      '试试下面的快捷问题，或直接输入。',
    ts: Date.now(),
    checked: true,
    intent: 'help',
    sources: [],
  })
  refreshKnowledge()
})
</script>

<template>
  <div class="page">
    <PageHeader
      title="智能分析"
      subtitle="基于真实识别统计的问答。回答只引用数据库里的数字，没有依据时明说「不知道」。"
      :breadcrumb="[{ text: '控制台', to: '/dashboard' }, { text: '智能分析' }]"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="对话" name="chat">
        <AppCard :padded="false" class="chat-card">
          <div class="chat-wrap">
            <!-- 消息流 -->
            <div ref="listRef" class="messages">
              <div
                v-for="(m, i) in messages"
                :key="i"
                class="message"
                :class="m.role === 'user' ? 'message--user' : 'message--assistant'"
              >
                <div class="message__avatar">
                  {{ m.role === 'user' ? (auth.user?.username?.[0] ?? '我').toUpperCase() : 'AI' }}
                </div>
                <div class="message__bubble">
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="message__content" v-html="formatMessage(m.content)" />
                  <div v-if="m.role === 'assistant' && m.intent" class="message__meta">
                    <span class="chip chip-primary">{{ intentLabel[m.intent] ?? m.intent }}</span>
                    <span v-if="m.checked === false" class="chip chip-warning">⚠ 数字待核对</span>
                    <span v-else-if="m.checked" class="chip chip-success">✓ 已对照统计</span>
                    <button v-if="can('chat.knowledge.write')" class="save-btn" @click="saveToKnowledge(m as ChatMessage)">✦ 存入知识库</button>
                  </div>
                </div>
              </div>

              <!-- 思考中 -->
              <div v-if="loading" class="message message--assistant">
                <div class="message__avatar">AI</div>
                <div class="message__bubble">
                  <div class="typing">
                    <span /><span /><span />
                  </div>
                </div>
              </div>
            </div>

            <!-- 快捷问题 -->
            <div class="suggests">
              <button
                v-for="s in SUGGESTIONS"
                :key="s"
                class="suggest"
                :disabled="loading"
                @click="send(s as any)"
              >
                {{ s }}
              </button>
            </div>

            <!-- 输入框 -->
            <div class="composer">
              <textarea
                v-model="input"
                class="composer__input"
                rows="2"
                placeholder="问问识别结果…（Enter 发送，Shift+Enter 换行）"
                @keydown.enter.exact.prevent="send()"
              />
              <button class="composer__send" :disabled="!input.trim() || loading" @click="send()">
                发送
                <span class="composer__arrow">→</span>
              </button>
            </div>
          </div>
        </AppCard>
      </el-tab-pane>

      <el-tab-pane :label="`知识库 (${knowledge.length})`" name="knowledge">
        <AppCard>
          <el-table v-if="knowledge.length" :data="knowledge" size="default">
            <el-table-column prop="id" label="#" width="80" />
            <el-table-column prop="question" label="问题" min-width="220" />
            <el-table-column label="回答" min-width="300">
              <template #default="{ row }">
                <div class="answer-preview">
                  {{ row.answer.slice(0, 120) }}{{ row.answer.length > 120 ? '…' : '' }}
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="120" />
            <el-table-column v-if="auth.isAdmin" label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="onDeleteKnowledge(row as KnowledgeEntry)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            title="暂无知识条目"
            description="在对话中点「存入知识库」，下次类似问题会被检索到"
            icon="✦"
          />
        </AppCard>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.chat-card {
  height: 680px;
}
.chat-wrap {
  display: flex;
  flex-direction: column;
  height: 680px;
}

/* 消息流 */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.message {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-start;
  animation: slide-up var(--t-base) var(--ease-decelerate);
}
.message--user {
  flex-direction: row-reverse;
}
.message__avatar {
  flex-shrink: 0;
  width: 32px; height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--r-full);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
}
.message--user .message__avatar {
  background: linear-gradient(135deg, var(--c-primary-400), var(--c-primary-600));
  color: white;
}
.message--assistant .message__avatar {
  background: var(--bg-subtle);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}
.message__bubble {
  max-width: 78%;
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-lg);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.message--user .message__bubble {
  background: var(--c-primary-50);
  border-color: var(--c-primary-100);
}
.message__content {
  font-size: var(--fs-md);
  line-height: var(--lh-relaxed);
  color: var(--text-primary);
}
.message__meta {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  margin-top: var(--sp-3);
  padding-top: var(--sp-2);
  border-top: 1px dashed var(--border-default);
}
.save-btn {
  background: transparent;
  border: none;
  padding: 2px var(--sp-2);
  border-radius: var(--r-sm);
  color: var(--text-accent);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.save-btn:hover {
  background: var(--c-primary-50);
}

/* 打字指示器 */
.typing {
  display: flex;
  gap: 4px;
  padding: var(--sp-1) 0;
}
.typing span {
  width: 6px; height: 6px;
  border-radius: var(--r-full);
  background: var(--c-neutral-400);
  animation: typing-bounce 1s ease-in-out infinite;
}
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-4px); opacity: 1; }
}

/* 快捷问题 */
.suggests {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-5);
  flex-wrap: wrap;
  border-top: 1px solid var(--border-default);
}
.suggest {
  padding: var(--sp-1) var(--sp-3);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-full);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.suggest:hover:not(:disabled) {
  background: var(--c-primary-50);
  border-color: var(--border-accent);
  color: var(--text-accent);
}
.suggest:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 输入 */
.composer {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-5);
  border-top: 1px solid var(--border-default);
  align-items: flex-end;
}
.composer__input {
  flex: 1;
  resize: none;
  padding: var(--sp-3);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--r-md);
  font: inherit;
  color: var(--text-primary);
  transition: all var(--t-fast) var(--ease-standard);
}
.composer__input:focus {
  outline: none;
  border-color: var(--border-focus);
  background: var(--bg-surface);
  box-shadow: var(--shadow-focus);
}
.composer__send {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-2) var(--sp-4);
  background: var(--c-primary-600);
  color: white;
  border: none;
  border-radius: var(--r-md);
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--t-fast) var(--ease-standard);
}
.composer__send:hover:not(:disabled) {
  background: var(--c-primary-700);
  transform: translateY(-1px);
}
.composer__send:disabled {
  background: var(--c-neutral-300);
  cursor: not-allowed;
}
.composer__arrow {
  transition: transform var(--t-fast) var(--ease-standard);
}
.composer__send:hover:not(:disabled) .composer__arrow {
  transform: translateX(3px);
}

/* chips */
.chip {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--sp-2);
  font-size: var(--fs-xs);
  font-weight: var(--fw-medium);
  border-radius: var(--r-full);
}
.chip-primary  { color: var(--c-primary-700);  background: var(--c-primary-50); }
.chip-success  { color: var(--c-success-600);  background: var(--c-success-50); }
.chip-warning  { color: var(--c-warning-600);  background: var(--c-warning-50); }

.answer-preview {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: var(--lh-normal);
}
</style>
