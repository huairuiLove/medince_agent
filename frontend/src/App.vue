<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import MainLayout from '@/components/layout/MainLayout.vue'

const route = useRoute()
const isPublic = computed(() => Boolean(route.meta.public))
</script>

<template>
  <MainLayout v-if="!isPublic">
    <RouterView />
  </MainLayout>
  <RouterView v-else />
</template>
