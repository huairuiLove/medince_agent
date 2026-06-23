<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const allLinks = [
  { to: '/', label: '系统概览' },
  { to: '/imaging', label: '影像与会诊' },
  { to: '/consult', label: '多智能体会诊' },
  { to: '/chat', label: '智能问答' },
  { to: '/rule-review', label: '规则审查' },
  { to: '/cpoe', label: 'CPOE 审查' },
  { to: '/drugs', label: '药品库' },
  { to: '/cases', label: '病例回放' },
  { to: '/agents', label: '智能体' },
  { to: '/pharmacy', label: '药师工作台' },
  { to: '/pharmacy/audit', label: 'Override 审计' },
  { to: '/settings', label: '个人配置' },
]

const links = computed(() => allLinks.filter(l => auth.navRoutes.includes(l.to)))

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <span class="logo">MS</span>
        <div>
          <strong>MedSafe</strong>
          <small>临床用药安全系统 v3</small>
        </div>
      </div>

      <div v-if="auth.profile" class="user-block">
        <strong>{{ auth.profile.display_name }}</strong>
        <small>{{ auth.department?.name_cn ?? auth.profile.dept_id }}</small>
      </div>

      <nav>
        <RouterLink
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          class="nav-link"
          :class="{ active: route.path === l.to || (l.to !== '/' && route.path.startsWith(l.to)) }"
        >
          {{ l.label }}
        </RouterLink>
      </nav>
      <footer class="sidebar-foot">
        <button type="button" class="logout" @click="logout">退出登录</button>
        <a href="/docs" target="_blank">API 文档</a>
      </footer>
    </aside>
    <main class="main">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 220px;
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  display: flex;
  flex-direction: column;
  padding: 1rem 0.75rem;
  flex-shrink: 0;
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0 0.4rem 1.25rem;
  border-bottom: 1px solid rgba(255,255,255,0.12);
  margin-bottom: 0.85rem;
}
.user-block {
  padding: 0 0.4rem 0.85rem;
  margin-bottom: 0.5rem;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  font-size: 0.82rem;
}
.user-block strong { display: block; color: #fff; }
.user-block small { color: #90a4be; }
.logo {
  width: 34px; height: 34px;
  background: var(--primary);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.75rem; font-weight: 800; color: #fff;
  letter-spacing: -0.02em;
}
.brand strong { display: block; color: #fff; font-size: 0.95rem; }
.brand small { font-size: 0.68rem; color: #90a4be; }
.nav-link {
  display: block;
  padding: 0.55rem 0.65rem;
  border-radius: var(--radius);
  color: #b0bec5;
  margin-bottom: 0.15rem;
  text-decoration: none;
  font-size: 0.88rem;
  border-left: 3px solid transparent;
}
.nav-link:hover { background: rgba(255,255,255,0.06); color: #fff; text-decoration: none; }
.nav-link.active {
  background: rgba(21, 101, 192, 0.35);
  color: #fff;
  border-left-color: #64b5f6;
}
.sidebar-foot { margin-top: auto; padding: 0.85rem 0.4rem; font-size: 0.78rem; display: flex; flex-direction: column; gap: 0.5rem; }
.logout {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.2);
  color: #b0bec5;
  padding: 0.35rem 0.5rem;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.78rem;
  text-align: left;
}
.logout:hover { color: #fff; border-color: rgba(255,255,255,0.4); }
.sidebar-foot a { color: #78909c; }
.main { flex: 1; padding: 1.25rem 1.75rem; overflow-x: hidden; }
@media (max-width: 768px) {
  .layout { flex-direction: column; }
  .sidebar { width: 100%; }
  .main { padding: 1rem; }
}
</style>
