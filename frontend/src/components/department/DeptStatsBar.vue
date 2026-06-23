<script setup lang="ts">
defineProps<{
  reviewsToday: number
  alertsToday: number
  overridesToday: number
  pendingQueue: number
}>()
</script>

<template>
  <div class="stats-bar card">
    <div class="stat">
      <span class="label">今日审查</span>
      <strong>{{ reviewsToday }}</strong>
    </div>
    <div class="stat">
      <span class="label">告警数</span>
      <strong class="warn">{{ alertsToday }}</strong>
    </div>
    <div class="stat">
      <span class="label">Override</span>
      <strong>{{ overridesToday }}</strong>
    </div>
    <div class="stat">
      <span class="label">待审队列</span>
      <strong>{{ pendingQueue }}</strong>
    </div>
  </div>
</template>

<style scoped>
.stats-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.25rem;
}
.stat { display: flex; flex-direction: column; gap: 0.25rem; }
.label { font-size: 0.78rem; color: var(--text-muted); }
strong { font-size: 1.35rem; }
.warn { color: var(--warning, #c27803); }
@media (max-width: 720px) {
  .stats-bar { grid-template-columns: repeat(2, 1fr); }
}
</style>
