import type { DrugItem, PatientContext } from '@/types'

export function mergeDrugIndicationsIntoDiagnoses(
  patient: PatientContext,
  candidateDrugs: DrugItem[],
): void {
  const merged = [...(patient.diagnoses ?? [])]
  const names = merged.map((d) => d.name)

  for (const drug of candidateDrugs) {
    const ind = drug.indication?.trim()
    if (!ind) continue

    const indLower = ind.toLowerCase()
    const idx = merged.findIndex((d) => {
      const nl = d.name.trim().toLowerCase()
      return nl === indLower || nl.includes(indLower) || indLower.includes(nl)
    })

    if (idx === -1) {
      merged.push({ name: ind })
      names.push(ind)
      continue
    }

    const existing = merged[idx].name.trim()
    if (
      ind.length > existing.length &&
      indLower.includes(existing.toLowerCase())
    ) {
      merged[idx] = { ...merged[idx], name: ind }
      names[idx] = ind
    }
  }

  patient.diagnoses = merged
}

export function drugsWithoutIndication(drugs: DrugItem[]): DrugItem[] {
  return drugs.map(({ indication: _ind, ...rest }) => ({ ...rest }))
}

export function drugDetailParts(drug: DrugItem): string[] {
  return [drug.dose, drug.route, drug.frequency].filter(Boolean) as string[]
}

const UNKNOWN_LIST_VALUES = new Set([
  'unknown', 'none', 'n/a', 'na', '无', '不详', '未知', 'nkda', '无过敏', '无已知', 'not known',
])

function repairCharSplitList(items: string[]): string[] {
  const stripped = items.map(s => s.trim()).filter(Boolean)
  if (stripped.length >= 2 && stripped.every(s => s.length === 1)) {
    return [stripped.join('')]
  }
  return stripped
}

/** Normalize LLM list fields that may arrive as strings or char-split arrays. */
export function coerceStringList(value: unknown): string[] {
  if (value == null) return []
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text || UNKNOWN_LIST_VALUES.has(text.toLowerCase())) return []
    if (/[,，;；\n]/.test(text)) {
      return repairCharSplitList(
        text.split(/[,，;；\n]+/).map(s => s.trim()).filter(Boolean),
      )
    }
    return [text]
  }
  if (Array.isArray(value)) {
    const result: string[] = []
    for (const item of value) {
      if (typeof item === 'string') {
        const s = item.trim()
        if (s) result.push(s)
      } else if (item && typeof item === 'object' && 'name' in item) {
        const s = String((item as { name?: string }).name ?? '').trim()
        if (s) result.push(s)
      } else if (item != null) {
        const s = String(item).trim()
        if (s) result.push(s)
      }
    }
    return repairCharSplitList(result)
  }
  const s = String(value).trim()
  return s ? [s] : []
}
