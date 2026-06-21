import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface ChatMessage {
  id: string
  role: string
  content: string
  tools?: Array<{ id: string; name: string; status: string; args?: unknown; result?: string }>
}

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
}

const DEFAULT_WELCOME =
  '你好！我是 MedSafe 用药安全助手。\n\n我可以帮你：\n- 检查多种药物之间的相互作用\n- 识别处方药、OTC、保健品之间的冲突\n- 评估特定人群（孕妇/老人/儿童）的用药风险\n- 提醒食物与药物的禁忌搭配\n\n请告诉我你正在服用什么药物，或直接点击下方的快捷问题开始。'

function createConversation(title = '新对话'): Conversation {
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
  return {
    id,
    title,
    messages: [{ id: '1', role: 'assistant', content: DEFAULT_WELCOME }],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  }
}

export const useConversationStore = defineStore('conversation', () => {
  const saved = (() => {
    try {
      const raw = localStorage.getItem('medsafe_conversations')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })()

  const conversations = ref<Conversation[]>(
    saved?.length ? saved : [createConversation('新对话')],
  )
  const activeId = ref<string>(conversations.value[0]?.id || '')

  const activeConversation = computed(
    () => conversations.value.find((c) => c.id === activeId.value) || conversations.value[0],
  )
  const sortedConversations = computed(() =>
    [...conversations.value].sort((a, b) => b.updatedAt - a.updatedAt),
  )

  function save() {
    try {
      localStorage.setItem('medsafe_conversations', JSON.stringify(conversations.value))
    } catch {
      /* quota exceeded */
    }
  }

  function newConversation() {
    const conv = createConversation()
    conversations.value.unshift(conv)
    activeId.value = conv.id
    save()
  }

  function switchTo(id: string) {
    if (conversations.value.find((c) => c.id === id)) activeId.value = id
  }

  function deleteConversation(id: string) {
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx === -1) return
    conversations.value.splice(idx, 1)
    if (activeId.value === id) activeId.value = conversations.value[0]?.id || ''
    if (conversations.value.length === 0) {
      const conv = createConversation()
      conversations.value.push(conv)
      activeId.value = conv.id
    }
    save()
  }

  function updateTitle(id: string, title: string) {
    const conv = conversations.value.find((c) => c.id === id)
    if (conv && title) {
      conv.title = title.slice(0, 30)
      save()
    }
  }

  function renameConversation(id: string, newTitle: string) {
    const conv = conversations.value.find((c) => c.id === id)
    if (conv && newTitle.trim()) {
      conv.title = newTitle.trim().slice(0, 30)
      save()
    }
  }

  function touch(id: string) {
    const conv = conversations.value.find((c) => c.id === id)
    if (conv) {
      conv.updatedAt = Date.now()
      save()
    }
  }

  return {
    conversations,
    activeId,
    activeConversation,
    sortedConversations,
    newConversation,
    switchTo,
    deleteConversation,
    updateTitle,
    renameConversation,
    touch,
  }
})
