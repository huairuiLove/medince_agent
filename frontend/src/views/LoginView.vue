<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import { useAuthStore } from '@/stores/auth'
import type { DepartmentInfo } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const deptId = ref('')
const departments = ref<DepartmentInfo[]>([])
const departmentsLoading = ref(true)
const localError = ref('')

onMounted(async () => {
  departmentsLoading.value = true
  try {
    departments.value = (await medsafeApi.listDepartments()).departments
    if (departments.value.length) {
      deptId.value = departments.value[0].dept_id
    }
  } catch {
    departments.value = []
    localError.value = '无法加载科室列表，请确认后端服务已启动'
  } finally {
    departmentsLoading.value = false
  }
})

async function submit() {
  localError.value = ''
  try {
    if (mode.value === 'login') {
      await auth.login(username.value, password.value)
    } else {
      await auth.register({
        username: username.value,
        password: password.value,
        display_name: displayName.value || username.value,
        dept_id: deptId.value,
      })
    }
    router.replace('/')
  } catch (e) {
    localError.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <div class="login-page">
    <div class="card login-card">
      <h1>MedSafe 医生工作台</h1>
      <p class="sub">登录后按科室加载影像数据，并保存您的专科智能体与审查专长配置</p>

      <div class="tabs">
        <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <form @submit.prevent="submit">
        <label class="field">
          <span>用户名</span>
          <input v-model="username" required autocomplete="username" minlength="2" maxlength="64" />
        </label>
        <label v-if="mode === 'register'" class="field">
          <span>显示名称</span>
          <input v-model="displayName" autocomplete="name" />
        </label>
        <label v-if="mode === 'register'" class="field">
          <span>科室</span>
          <select
            v-model="deptId"
            class="select"
            required
            :disabled="departmentsLoading || !departments.length"
          >
            <option value="" disabled>{{ departmentsLoading ? '加载科室…' : '请选择科室' }}</option>
            <option v-for="d in departments" :key="d.dept_id" :value="d.dept_id">
              {{ d.name_cn }} ({{ d.dept_id }})
            </option>
          </select>
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="password" type="password" required autocomplete="current-password" minlength="6" maxlength="128" />
        </label>

        <p v-if="localError || auth.error" class="err">{{ localError || auth.error }}</p>

        <button class="btn-primary full" type="submit" :disabled="auth.loading">
          {{ auth.loading ? '处理中…' : mode === 'login' ? '登录' : '注册并登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0d2137 0%, #1a3a5c 100%);
  padding: 1.5rem;
}
.login-card {
  width: 100%;
  max-width: 420px;
  padding: 1.75rem;
}
.sub { color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1.25rem; }
.tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.tabs button {
  flex: 1;
  padding: 0.45rem;
  border: 1px solid var(--border);
  background: var(--surface-2);
  border-radius: var(--radius);
  cursor: pointer;
}
.tabs button.active { background: var(--primary-light); border-color: var(--primary); color: var(--primary-dark); }
.field { display: block; margin-bottom: 0.85rem; }
.field span { display: block; font-size: 0.82rem; margin-bottom: 0.25rem; color: var(--text-muted); }
.field input, .field select { width: 100%; padding: 0.5rem 0.65rem; border: 1px solid var(--border); border-radius: var(--radius); }
.err { color: var(--danger); font-size: 0.85rem; margin: 0.5rem 0; }
code { font-family: var(--mono); font-size: 0.78rem; }
</style>
