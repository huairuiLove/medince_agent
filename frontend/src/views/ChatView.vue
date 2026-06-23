<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { useConversationStore } from '@/stores/conversation'

type UserRole = 'doctor' | 'patient'

const convStore = useConversationStore()
const conv = computed(() => convStore.activeConversation)
const role = ref<UserRole>('patient')
const inputText = ref('')
const isLoading = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const sidebarOpen = ref(false)

const roleLabel = computed(() =>
  role.value === 'doctor' ? '专业模式（医护）' : '大众模式（患者）',
)

function toggleRole() {
  role.value = role.value === 'doctor' ? 'patient' : 'doctor'
  const label =
    role.value === 'doctor'
      ? '已切换到专业模式 — 使用医学术语和证据等级'
      : '已切换到大众模式 — 使用通俗语言，更易懂'
  conv.value?.messages.push({
    id: 'sys_' + Date.now(),
    role: 'assistant',
    content: '_' + label + '_',
  })
  convStore.touch(conv.value!.id)
  scrollToBottom(true)
}

function toolLabel(name: string): string {
  if (name.includes('interaction')) return '相互作用检查'
  if (name.includes('drug')) return '药品查询'
  if (name.includes('review')) return '处方审查'
  if (name.includes('contraindication')) return '禁忌排查'
  if (name.includes('alternative')) return '替代方案'
  if (name.includes('knowledge') || name.includes('graph')) return '知识图谱'
  return '工具调用'
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const el = messagesRef.value
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (force || atBottom) el.scrollTop = el.scrollHeight
  })
}

watch(() => conv.value?.messages.length, () => scrollToBottom())

function quickAsk(q: string) {
  inputText.value = q
  nextTick(() => send())
}

async function send() {
  if (!inputText.value.trim() || isLoading.value || !conv.value) return
  const c = conv.value
  const userContent = inputText.value

  c.messages.push({ id: Date.now().toString(), role: 'user', content: userContent })
  inputText.value = ''
  isLoading.value = true
  convStore.updateTitle(c.id, userContent)
  convStore.touch(c.id)
  scrollToBottom(true)

  try {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: c.messages
          .filter((m) => !String(m.id).startsWith('sys_'))
          .map((m) => ({ role: m.role, content: m.content })),
        role: role.value,
      }),
    })

    if (!response.ok) {
      let detail = response.statusText
      try {
        const err = await response.json()
        detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail ?? err)
      } catch {
        detail = await response.text().catch(() => detail)
      }
      const hint =
        response.status === 503
          ? `LLM 未配置或不可用（503）：${detail}。请在 config.yaml 配置 chat.api_key 后重启后端。`
          : `请求失败（HTTP ${response.status}）：${detail}`
      throw new Error(hint)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''
    const assistantMsg = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      tools: [] as Array<{ id: string; name: string; status: string }>,
    }
    c.messages.push(assistantMsg)

    let done = false
    while (!done) {
      const { done: sDone, value } = await reader.read()
      if (sDone) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        const em = part.match(/event: (\w+)/)
        const dm = part.match(/data: (.+)/s)
        if (!em || !dm) continue
        let data: Record<string, unknown>
        try {
          data = JSON.parse(dm[1])
        } catch {
          continue
        }
        if (em[1] === 'token') assistantMsg.content += (data.token as string) || ''
        else if (em[1] === 'tool') {
          const ex = assistantMsg.tools?.find((t) => t.id === data.id)
          if (ex) Object.assign(ex, data)
          else assistantMsg.tools?.push(data as { id: string; name: string; status: string })
        }         else if (em[1] === 'done') done = true
        else if (em[1] === 'error')
          assistantMsg.content += '\n[' + (data.message as string) + ']'
      }
      scrollToBottom()
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    c.messages.push({
      id: (Date.now() + 2).toString(),
      role: 'assistant',
      content: '[连接失败: ' + msg + '。请确认后端已启动。]',
    })
  } finally {
    isLoading.value = false
    convStore.touch(c.id)
    scrollToBottom(true)
  }
}
</script>

<template>
  <div class="chat-page">
    <header class="chat-header">
      <div>
        <h1>智能问答</h1>
        <p class="subtitle">ReAct + Graph RAG · 按角色差异化回答</p>
      </div>
      <div class="header-actions">
        <button class="role-toggle" :class="role" @click="toggleRole" :title="'切换至' + (role === 'doctor' ? '大众模式' : '专业模式')">
          {{ role === 'doctor' ? '🩺' : '👤' }} {{ roleLabel }}
        </button>
        <button class="btn-secondary" @click="convStore.newConversation()">新对话</button>
        <button class="btn-icon" @click="sidebarOpen = !sidebarOpen" title="历史对话">☰</button>
      </div>
    </header>

    <div class="chat-body">
      <aside v-show="sidebarOpen" class="conv-sidebar">
        <div
          v-for="item in convStore.sortedConversations"
          :key="item.id"
          :class="['conv-item', { active: item.id === convStore.activeId }]"
          @click="convStore.switchTo(item.id)"
        >
          <span class="conv-title">{{ item.title }}</span>
          <button class="conv-del" @click.stop="convStore.deleteConversation(item.id)">×</button>
        </div>
      </aside>

      <div class="chat-main">
        <div class="messages" ref="messagesRef">
          <div v-if="conv && conv.messages.length === 0" class="welcome">
            <div class="mode-badge" :class="role" @click="toggleRole">
              {{ roleLabel }} · 点击切换
            </div>
            <h2>{{ role === 'doctor' ? '专业用药安全决策支持' : '您的 AI 用药安全助手' }}</h2>
            <p>
              {{
                role === 'doctor'
                  ? '输入处方药物和患者情况，我将进行 Graph RAG 检索与工具调用，提供循证决策支持。'
                  : '告诉我你在服用什么药，我帮你看看有没有需要注意的地方。'
              }}
            </p>
            <div class="pills">
              <button class="pill" @click="quickAsk('华法林和布洛芬能一起吃吗？')">药物冲突检查</button>
              <button class="pill" @click="quickAsk('我有高血压和痛风，能吃布洛芬吗？')">禁忌症咨询</button>
              <button class="pill" @click="quickAsk('我在吃降压药、他汀、阿司匹林，帮我审查处方')">处方审查</button>
            </div>
          </div>

          <div v-for="(msg, idx) in conv?.messages" :key="msg.id" :class="['msg-row', msg.role, { system: String(msg.id).startsWith('sys_') }]">
            <div v-if="!String(msg.id).startsWith('sys_')" class="avatar">{{ msg.role === 'user' ? '👤' : '💊' }}</div>
            <div class="bubble" :class="{ system: String(msg.id).startsWith('sys_') }">
              <div class="content" v-html="msg.content ? renderMarkdown(msg.content) : ''" />
              <div v-if="msg.tools?.length" class="tools">
                <span v-for="t in msg.tools" :key="t.id" class="tool-chip">
                  {{ t.status === 'calling' ? '⏳' : '✅' }} {{ toolLabel(t.name) }}
                </span>
              </div>
              <span v-if="isLoading && msg.role === 'assistant' && idx === (conv?.messages.length ?? 0) - 1" class="cursor">▊</span>
            </div>
          </div>
        </div>

        <div class="input-area">
          <input
            v-model="inputText"
            :placeholder="role === 'doctor' ? '输入处方药物和患者信息...' : '输入你正在服用的药物...'"
            :disabled="isLoading"
            @keyup.enter="send"
          />
          <button class="send-btn" :disabled="isLoading || !inputText.trim()" @click="send">发送</button>
        </div>
        <p class="disclaimer">MedSafe 提供 AI 辅助建议，不可替代专业医师诊断。紧急情况请拨打 120。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 2.5rem);
  margin: -1.25rem -1.75rem;
  background: var(--bg, #f0f4f8);
}
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: #fff;
  border-bottom: 1px solid var(--border, #e0e6ed);
}
.chat-header h1 { font-size: 1.15rem; margin: 0; color: var(--text, #1a2332); }
.subtitle { font-size: 0.78rem; color: var(--muted, #64748b); margin: 0.2rem 0 0; }
.header-actions { display: flex; gap: 0.5rem; align-items: center; }
.role-toggle {
  border: 1px solid var(--border);
  background: #fff;
  padding: 0.35rem 0.75rem;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.82rem;
}
.role-toggle.doctor { border-color: #1565c0; color: #1565c0; background: #e3f2fd; }
.role-toggle.patient { border-color: #2e7d32; color: #2e7d32; background: #e8f5e9; }
.btn-secondary {
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.82rem;
}
.btn-icon { border: none; background: transparent; font-size: 1.2rem; cursor: pointer; padding: 0.25rem; }
.chat-body { flex: 1; display: flex; min-height: 0; }
.conv-sidebar {
  width: 200px;
  background: #fff;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 0.5rem;
}
.conv-item {
  display: flex;
  align-items: center;
  padding: 0.5rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.82rem;
}
.conv-item:hover { background: #f5f7fa; }
.conv-item.active { background: #e3f2fd; }
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-del { border: none; background: none; color: #999; cursor: pointer; opacity: 0; }
.conv-item:hover .conv-del { opacity: 1; }
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.messages { flex: 1; overflow-y: auto; padding: 1rem 1.5rem; }
.welcome { text-align: center; padding: 2rem 1rem; max-width: 560px; margin: 0 auto; }
.mode-badge {
  display: inline-block;
  padding: 0.35rem 0.85rem;
  border-radius: 20px;
  font-size: 0.82rem;
  cursor: pointer;
  margin-bottom: 1rem;
}
.mode-badge.doctor { background: #e3f2fd; color: #1565c0; }
.mode-badge.patient { background: #e8f5e9; color: #2e7d32; }
.welcome h2 { font-size: 1.35rem; font-weight: 500; margin-bottom: 0.5rem; }
.welcome p { color: var(--muted); font-size: 0.9rem; line-height: 1.6; margin-bottom: 1.25rem; }
.pills { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center; }
.pill {
  padding: 0.45rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-size: 0.82rem;
}
.pill:hover { border-color: var(--primary, #1565c0); color: var(--primary); }
.msg-row { display: flex; gap: 0.65rem; max-width: 780px; margin: 0 auto 1rem; }
.msg-row.user { flex-direction: row-reverse; }
.msg-row.system { justify-content: center; }
.avatar { font-size: 1.1rem; flex-shrink: 0; }
.bubble {
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: #fff;
  border: 1px solid var(--border);
  max-width: 85%;
  line-height: 1.6;
  font-size: 0.9rem;
}
.msg-row.user .bubble { background: var(--primary, #1565c0); color: #fff; border-color: transparent; }
.bubble.system { background: #e3f2fd; color: #1565c0; font-size: 0.78rem; border: none; }
.bubble :deep(h2), .bubble :deep(h3) { margin: 0.5rem 0 0.35rem; font-size: 1rem; }
.bubble :deep(p) { margin: 0.35rem 0; }
.bubble :deep(ul) { padding-left: 1.25rem; }
.msg-row.user .bubble :deep(a) { color: #bbdefb; }
.tools { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.5rem; }
.tool-chip { font-size: 0.72rem; padding: 0.15rem 0.5rem; background: #f1f5f9; border-radius: 10px; color: #64748b; }
.cursor { color: var(--primary); animation: blink 1s infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.input-area {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  background: #fff;
  border-top: 1px solid var(--border);
  max-width: 820px;
  margin: 0 auto;
  width: 100%;
}
.input-area input {
  flex: 1;
  padding: 0.65rem 1rem;
  border: 1px solid var(--border);
  border-radius: 24px;
  outline: none;
  font-size: 0.9rem;
}
.input-area input:focus { border-color: var(--primary); }
.send-btn {
  padding: 0.65rem 1.25rem;
  background: var(--primary, #1565c0);
  color: #fff;
  border: none;
  border-radius: 24px;
  cursor: pointer;
  font-size: 0.9rem;
}
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.disclaimer { text-align: center; font-size: 0.72rem; color: #94a3b8; padding: 0.35rem 0 0.75rem; }
</style>
