<script setup lang="ts">
import type { CpoeReviewAlert } from '@/types'

const props = defineProps<{
  alerts: CpoeReviewAlert[]
  focusCategories: string[]
}>()

function isFocus(alert: CpoeReviewAlert) {
  if (!props.focusCategories.length) return false
  return props.focusCategories.includes(alert.category ?? '')
}
</script>

<template>
  <section v-if="alerts.some(isFocus)" class="focus card">
    <h3>科室关注</h3>
    <ul>
      <li v-for="a in alerts.filter(isFocus)" :key="a.alert_id">
        <strong>{{ a.category }}</strong> — {{ a.summary }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.focus { margin-bottom: 1rem; border-left: 3px solid var(--primary); }
.focus h3 { margin: 0 0 0.5rem; font-size: 0.95rem; }
ul { margin: 0; padding-left: 1.1rem; font-size: 0.88rem; }
li { margin-bottom: 0.35rem; }
</style>
