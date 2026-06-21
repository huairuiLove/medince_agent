import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    { path: '/consult', name: 'consult', component: () => import('@/views/ConsultView.vue') },
    { path: '/rule-review', name: 'rule-review', component: () => import('@/views/RuleReviewView.vue') },
    { path: '/cases', name: 'cases', component: () => import('@/views/CasesView.vue') },
    { path: '/cases/:id', name: 'case-detail', component: () => import('@/views/CaseDetailView.vue') },
    { path: '/agents', name: 'agents', component: () => import('@/views/AgentsView.vue') },
    { path: '/imaging', name: 'imaging', component: () => import('@/views/ImagingView.vue') },
  ],
})

export default router
