<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { addKnowledge, askChat, deleteKnowledge, listKnowledge } from '@/api/chat'
import type { ChatMessage, KnowledgeEntry } from '@/api/chat'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
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
    ElMessage.success('已存入知识库')
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
  // Escape before re-introducing any markup, so user text can never inject HTML.
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
      '你好，我是 VisionFlywheel 的智能分析助手。我可以基于真实识别数据回答问题——\n\n' +
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
  <div class="page chat">
    <h2>智能分析</h2>
    <p class="lead">
      基于真实识别统计的问答。回答只引用数据库里的数字，没有依据时明说"不知道"。
    </p>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="对话" name="chat">
        <div class="chat-wrap">
          <div ref="listRef" class="messages">
            <div
              v-for="(m, i) in messages"
              :key="i"
              class="message"
              :class="m.role === 'user' ? 'user' : 'assistant'"
            >
              <div class="role">{{ m.role === 'user' ? '我' : '助手' }}</div>
              <div class="bubble">
                <!-- eslint-disable-next-line vue/no-v-html -- content is HTML-escaped in formatMessage -->
                <div class="content" v-html="formatMessage(m.content)" />
                <div v-if="m.role === 'assistant' && m.intent" class="meta">
                  <el-tag size="small" type="info">{{ intentLabel[m.intent] ?? m.intent }}</el-tag>
                  <el-tag v-if="m.checked === false" size="small" type="warning">数字待核对</el-tag>
                  <el-tag v-else-if="m.checked" size="small" type="success">已对照统计</el-tag>
                  <el-button size="small" text type="primary" @click="saveToKnowledge(m)">存入知识库</el-button>
                </div>
              </div>
            </div>
            <div v-if="loading" class="message assistant">
              <div class="role">助手</div>
              <div class="bubble loading">思考中…</div>
            </div>
          </div>

          <div class="suggests">
            <el-tag
              v-for="s in SUGGESTIONS"
              :key="s"
              size="small"
              class="suggest"
              @click="send(s)"
            >
              {{ s }}
            </el-tag>
          </div>

          <div class="composer">
            <el-input
              v-model="input"
              :rows="2"
              type="textarea"
              placeholder="问问识别结果…（Enter 发送，Shift+Enter 换行）"
              @keydown.enter.exact.prevent="send()"
            />
            <el-button type="primary" :loading="loading" @click="send()">发送</el-button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane :label="`知识库 (${knowledge.length})`" name="knowledge">
        <el-table :data="knowledge" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="question" label="问题" min-width="200" />
          <el-table-column prop="answer" label="回答" min-width="280">
            <template #default="{ row }">
              <div class="answer-preview">{{ row.answer.slice(0, 120) }}{{ row.answer.length > 120 ? '…' : '' }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="source" label="来源" width="110" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                v-if="auth.isAdmin"
                size="small"
                text
                type="danger"
                @click="onDeleteKnowledge(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!knowledge.length" description="暂无知识条目，可在对话中点「存入知识库」" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.lead {
  color: var(--vf-ink-muted);
}
.chat-wrap {
  display: flex;
  flex-direction: column;
  height: 620px;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.message.user {
  flex-direction: row-reverse;
}
.role {
  font-size: 11px;
  color: var(--vf-ink-muted);
  width: 32px;
  text-align: center;
  padding-top: 6px;
  flex-shrink: 0;
}
.bubble {
  background: var(--vf-surface);
  border: 1px solid var(--vf-border);
  border-radius: 12px;
  padding: 10px 14px;
  max-width: 80%;
}
.message.user .bubble {
  background: var(--vf-accent-soft);
  border-color: var(--vf-accent);
}
.bubble.loading {
  color: var(--vf-ink-muted);
  font-style: italic;
}
.content {
  font-size: 13px;
  line-height: 1.6;
}
.meta {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.suggests {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 0;
}
.suggest {
  cursor: pointer;
}
.suggest:hover {
  border-color: var(--vf-accent);
}
.composer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding-top: 8px;
  border-top: 1px solid var(--vf-border);
}
.answer-preview {
  font-size: 12px;
  color: var(--vf-ink-muted);
}
</style>
