import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import type { DepartmentInfo, DoctorWorkspace, UserProfile } from '@/types'

const TOKEN_KEY = 'medsafe_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const workspace = ref<DoctorWorkspace | null>(null)
  const loading = ref(false)
  const error = ref('')

  const isLoggedIn = computed(() => Boolean(token.value))
  const profile = computed<UserProfile | null>(() => workspace.value?.profile ?? null)
  const department = computed<DepartmentInfo | null>(() => profile.value?.department ?? null)
  const navRoutes = computed(() => {
    const routes = department.value?.nav_routes
    if (routes?.length) return routes
    return ['/', '/department', '/imaging', '/consult', '/chat', '/rule-review', '/cpoe', '/drugs', '/cases', '/agents', '/settings']
  })

  function setToken(value: string | null) {
    token.value = value
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  }

  async function login(username: string, password: string) {
    loading.value = true
    error.value = ''
    try {
      const res = await medsafeApi.login(username, password)
      setToken(res.access_token)
      await fetchMe()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function register(body: { username: string; password: string; display_name?: string; dept_id: string }) {
    loading.value = true
    error.value = ''
    try {
      const res = await medsafeApi.register(body)
      setToken(res.access_token)
      workspace.value = {
        profile: res.profile,
        agents: res.agents,
        custom_skills: res.custom_skills,
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!token.value) {
      workspace.value = null
      return
    }
    workspace.value = await medsafeApi.getMe()
  }

  async function saveAgentPrefs(agents: { agent_id: string; enabled: boolean }[]) {
    workspace.value = await medsafeApi.updateAgentPrefs({ agents })
  }

  async function saveSkillPrefs(skills: { agent_id: string; skill_id: string; enabled: boolean }[]) {
    workspace.value = await medsafeApi.updateSkillPrefs({ skills })
  }

  async function addCustomSkill(body: { agent_id: string; title: string; content_md: string }) {
    await medsafeApi.addCustomSkill(body)
    await fetchMe()
  }

  function logout() {
    setToken(null)
    workspace.value = null
  }

  return {
    token,
    workspace,
    loading,
    error,
    isLoggedIn,
    profile,
    department,
    navRoutes,
    login,
    register,
    fetchMe,
    saveAgentPrefs,
    saveSkillPrefs,
    addCustomSkill,
    logout,
  }
})
