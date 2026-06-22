import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    { path: '/consult', name: 'consult', component: () => import('@/views/ConsultView.vue') },
    { path: '/chat', name: 'chat', component: () => import('@/views/ChatView.vue') },
    { path: '/rule-review', name: 'rule-review', component: () => import('@/views/RuleReviewView.vue') },
    { path: '/drugs', name: 'drugs', component: () => import('@/views/DrugDatabaseView.vue') },
    { path: '/cases', name: 'cases', component: () => import('@/views/CasesView.vue') },
    { path: '/cases/:id', name: 'case-detail', component: () => import('@/views/CaseDetailView.vue') },
    { path: '/agents', name: 'agents', component: () => import('@/views/AgentsView.vue') },
    { path: '/imaging', name: 'imaging', component: () => import('@/views/ImagingView.vue') },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/pharmacy', name: 'pharmacy', component: () => import('@/views/PharmacyWorkbenchView.vue') },
    { path: '/pharmacy/review/:id', name: 'pharmacy-review', component: () => import('@/views/PharmacyReviewDetailView.vue') },
    { path: '/pharmacy/audit', name: 'pharmacy-audit', component: () => import('@/views/OverrideAuditView.vue') },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.isLoggedIn) return { path: '/' }
    return true
  }
  if (!auth.isLoggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  if (!auth.workspace) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return { path: '/login' }
    }
  }
  const allowed = auth.navRoutes
  if (to.path !== '/' && !allowed.some(r => r === to.path || (r !== '/' && to.path.startsWith(r)))) {
    if (allowed.includes('/')) return { path: '/' }
    return { path: allowed[0] ?? '/settings' }
  }
  return true
})

export default router
