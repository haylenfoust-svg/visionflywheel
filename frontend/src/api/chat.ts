/** Chat / knowledge API client. */

import { apiGet, apiPost, apiDelete } from './http'

export interface ChatReply {
  answer: string
  sources: string[]
  intent: string
  is_hallucination_checked: boolean
}

export interface KnowledgeEntry {
  id: number
  question: string
  answer: string
  source: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  intent?: string
  checked?: boolean
  ts: number
}

export async function askChat(question: string): Promise<ChatReply> {
  return apiPost<ChatReply>('/api/chat', { question })
}

export async function addKnowledge(question: string, answer: string): Promise<KnowledgeEntry> {
  return apiPost<KnowledgeEntry>('/api/chat/knowledge', { question, answer })
}

export async function listKnowledge(): Promise<KnowledgeEntry[]> {
  return apiGet<KnowledgeEntry[]>('/api/knowledge')
}

export async function deleteKnowledge(id: number): Promise<void> {
  await apiDelete(`/api/knowledge/${id}`)
}
