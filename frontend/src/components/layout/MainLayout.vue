<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()

const links = [
  { to: '/', label: '系统概览' },
  { to: '/imaging', label: '影像与会诊' },
  { to: '/consult', label: '多智能体会诊' },
  { to: '/chat', label: '智能问答' },
  { to: '/rule-review', label: '规则审查' },
  { to: '/cases', label: '病例回放' },
  { to: '/agents', label: '智能体' },
]
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
.sidebar-foot { margin-top: auto; padding: 0.85rem 0.4rem; font-size: 0.78rem; }
.sidebar-foot a { color: #78909c; }
.main { flex: 1; padding: 1.25rem 1.75rem; overflow-x: hidden; }
@media (max-width: 768px) {
  .layout { flex-direction: column; }
  .sidebar { width: 100%; }
  .main { padding: 1rem; }
}
</style>
