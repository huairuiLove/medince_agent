import { ref } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import type { MultiConsultResponse, PatientContext, DrugItem } from '@/types'

export function useMultiConsult() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const result = ref<MultiConsultResponse | null>(null)

  async function run(payload: {
    text?: string
    patient_context?: PatientContext
    candidate_drugs: DrugItem[]
    unable_to_answer?: boolean
    persist?: boolean
  }) {
    loading.value = true
    error.value = null
    try {
      result.value = await medsafeApi.multiConsult(payload)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      result.value = null
    } finally {
      loading.value = false
    }
  }

  function reset() {
    result.value = null
    error.value = null
  }

  return { loading, error, result, run, reset }
}
