<script setup lang="ts">
import type { RiskLevel } from '@/types'

defineProps<{ level: RiskLevel; block?: boolean }>()

const map: Record<RiskLevel, string> = {
  high: 'badge-high',
  medium: 'badge-medium',
  low: 'badge-low',
  none: 'badge-none',
  unknown: 'badge-unknown',
}
</script>

<template>
  <span class="badge" :class="map[level]">
    {{ level }}
    <template v-if="block"> · BLOCK</template>
  </span>
</template>
