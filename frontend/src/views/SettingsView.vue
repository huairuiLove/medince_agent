<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const saving = ref(false)
const customAgentId = ref('clinical_pharmacist')
const customTitle = ref('')
const customContent = ref('')
const message = ref('')

const agents = computed(() => auth.workspace?.agents ?? [])
const customSkills = computed(() => auth.workspace?.custom_skills ?? [])

onMounted(async () => {
  if (!auth.workspace) await auth.fetchMe()
})

async function toggleAgent(agentId: string, enabled: boolean) {
  saving.value = true
  message.value = ''
  try {
    const updates = agents.value.map(a => ({
      agent_id: a.agent_id,
      enabled: a.agent_id === agentId ? enabled : Boolean(a.enabled),
    }))
    await auth.saveAgentPrefs(updates)
    message.value = '智能体配置已保存'
  } finally {
    saving.value = false
  }
}

async function toggleSkill(agentId: string, skillId: string, enabled: boolean) {
  saving.value = true
  message.value = ''
  try {
    const agent = agents.value.find(a => a.agent_id === agentId)
    if (!agent) return
    const updates = (agent.available_skills ?? []).map(s => ({
      agent_id: agentId,
      skill_id: s.skill_id,
      enabled: s.skill_id === skillId ? enabled : Boolean(s.enabled),
    }))
    await auth.saveSkillPrefs(updates)
    message.value = '审查专长配置已保存'
  } finally {
    saving.value = false
  }
}

async function addCustomSkill() {
  if (!customTitle.value.trim() || !customContent.value.trim()) return
  saving.value = true
  message.value = ''
  try {
    await auth.addCustomSkill({
      agent_id: customAgentId.value,
      title: customTitle.value.trim(),
      content_md: customContent.value.trim(),
    })
    customTitle.value = ''
    customContent.value = ''
    message.value = '自定义审查专长已添加'
  } finally {
    saving.value = false
  }
}

function visibleSkills(agent: (typeof agents.value)[number]) {
  return (agent.available_skills ?? []).filter(s => s.skill_id !== 'base')
}
</script>

<template>
  <div>
    <h1>个人智能体与审查专长</h1>
    <p class="sub">
      配置保存在 SQLite（<code>data/auth/medsafe_auth.db</code>），仅对您的账号生效。
      多智能体会诊时将按您启用的<strong>专科智能体</strong>与<strong>审查专长</strong>组合 prompt。
    </p>

    <p v-if="message" class="ok">{{ message }}</p>

    <section v-if="auth.department" class="card dept-card">
      <h2>{{ auth.department.name_cn }} · 科室专科视图</h2>
      <p class="dept-lock">
        科室在注册时绑定，登录后<strong>不可切换</strong>。如需更换科室，请先
        <button type="button" class="linkish" @click="auth.logout(); router.push('/login')">退出登录</button>
        并使用新科室账号重新注册/登录。
      </p>
      <p>{{ auth.department.description }}</p>
      <div class="chips">
        <span v-for="src in auth.department.imaging_sources" :key="src" class="chip">{{ src }}</span>
        <span v-if="!auth.department.imaging_sources?.length" class="chip muted">无默认影像源</span>
      </div>
      <div v-if="auth.department.recommended_datasets?.length" class="datasets">
        <h3>推荐数据集</h3>
        <ul>
          <li v-for="ds in auth.department.recommended_datasets" :key="ds.id">
            <strong>{{ ds.name }}</strong> ({{ ds.modality }}) — {{ ds.notes || ds.url }}
          </li>
        </ul>
      </div>
      <div v-if="auth.department.vision_models?.length" class="datasets">
        <h3>推荐视觉模型</h3>
        <ul>
          <li v-for="vm in auth.department.vision_models" :key="vm.model_id">
            <strong>{{ vm.name }}</strong> — {{ vm.task }}
            <small v-if="vm.download">{{ vm.download }}</small>
          </li>
        </ul>
      </div>
    </section>

    <div class="grid">
      <article
        v-for="a in agents"
        :key="a.agent_id"
        class="card agent-card"
        :class="{ dept: a.is_department_agent }"
      >
        <header>
          <label class="toggle">
            <input type="checkbox" :checked="a.enabled" @change="toggleAgent(a.agent_id, ($event.target as HTMLInputElement).checked)" />
            <strong>{{ a.agent_name }}</strong>
          </label>
          <span v-if="a.is_department_agent" class="badge dept-badge">科室专科</span>
        </header>
        <p class="role">{{ a.role }}</p>
        <h4>审查专长</h4>
        <p v-if="!visibleSkills(a).length" class="muted">暂无额外专长模块</p>
        <label v-for="s in visibleSkills(a)" :key="s.skill_id" class="skill-row">
          <input
            type="checkbox"
            :checked="s.enabled"
            @change="toggleSkill(a.agent_id, s.skill_id, ($event.target as HTMLInputElement).checked)"
          />
          <span class="skill-label">
            <strong>{{ s.title }}</strong>
            <small v-if="s.description">{{ s.description }}</small>
          </span>
        </label>
      </article>
    </div>

    <section class="card custom-section">
      <h2>添加自定义审查专长</h2>
      <p class="hint">用 Markdown 编写本院或本科室特有的审查要点，绑定到对应智能体。</p>
      <label class="field">
        绑定智能体
        <select v-model="customAgentId">
          <option v-for="a in agents" :key="a.agent_id" :value="a.agent_id">{{ a.agent_name }}</option>
        </select>
      </label>
      <label class="field">
        专长名称
        <input v-model="customTitle" placeholder="例如：本院抗菌药物分级审查" />
      </label>
      <label class="field">
        审查要点（Markdown）
        <textarea v-model="customContent" rows="5" placeholder="审查范围、监测指标、本院规范…" />
      </label>
      <button class="btn-primary" :disabled="saving" @click="addCustomSkill">保存自定义专长</button>

      <div v-if="customSkills.length" class="custom-list">
        <h3>已有自定义专长</h3>
        <ul>
          <li v-for="c in customSkills" :key="c.skill_id">
            <strong>{{ c.title }}</strong> → {{ c.agent_id }}
            <pre>{{ c.content_md.slice(0, 120) }}{{ c.content_md.length > 120 ? '…' : '' }}</pre>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sub { color: var(--text-muted); margin-bottom: 1rem; }
.hint { font-size: 0.85rem; color: var(--text-muted); margin: -0.25rem 0 0.75rem; }
.ok { color: var(--success, #2e7d32); margin-bottom: 1rem; }
.dept-card { margin-bottom: 1.25rem; }
.dept-lock { font-size: 0.88rem; color: var(--text-muted); margin-bottom: 0.5rem; }
.linkish { background: none; border: none; padding: 0; color: var(--primary); cursor: pointer; text-decoration: underline; font: inherit; }
.chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.5rem; }
.chip { background: var(--primary-light); color: var(--primary-dark); padding: 0.2rem 0.55rem; border-radius: 999px; font-size: 0.78rem; }
.chip.muted { background: var(--surface-2); color: var(--text-muted); }
.datasets { margin-top: 0.75rem; font-size: 0.88rem; }
.datasets ul { margin: 0.35rem 0 0 1rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
.agent-card header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; gap: 0.5rem; }
.agent-card.dept { border-color: #a5d6a7; background: linear-gradient(180deg, #f1f8f4 0%, var(--surface) 40%); }
.toggle { display: flex; gap: 0.5rem; align-items: center; cursor: pointer; }
.badge { font-size: 0.72rem; padding: 0.15rem 0.45rem; border-radius: 999px; flex-shrink: 0; }
.dept-badge { background: #e8f4ea; color: #1b5e20; }
.role { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.75rem; }
h4 { font-size: 0.88rem; margin: 0 0 0.5rem; }
.skill-row { display: flex; gap: 0.55rem; font-size: 0.85rem; margin-bottom: 0.55rem; cursor: pointer; align-items: flex-start; }
.skill-label { display: flex; flex-direction: column; gap: 0.15rem; }
.skill-label small { color: var(--text-muted); line-height: 1.35; }
.muted { color: var(--text-muted); font-size: 0.85rem; }
.custom-section { margin-top: 1.5rem; }
.field { display: block; margin-bottom: 0.75rem; font-size: 0.85rem; }
.field input, .field select, .field textarea { width: 100%; margin-top: 0.25rem; padding: 0.45rem; border: 1px solid var(--border); border-radius: var(--radius); }
.custom-list pre { font-size: 0.75rem; background: var(--surface-2); padding: 0.35rem; border-radius: var(--radius); white-space: pre-wrap; }
</style>
