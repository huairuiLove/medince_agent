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
