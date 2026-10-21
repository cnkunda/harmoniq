import type {
  DrillSlotPayload,
  PlanSlotIntent,
  PracticePlanPayload,
  PracticeSlotType,
} from '@/src/types'

type UnknownRecord = Record<string, unknown>

const SLOT_TYPES: readonly PracticeSlotType[] = ['warmup', 'technique', 'song_section', 'free_jam']
const SLOT_INTENTS: readonly PlanSlotIntent[] = ['practice', 'remediation', 'review']

function createId(): string {
  const cryptoObj = globalThis.crypto
  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') return cryptoObj.randomUUID()
  return `plan-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function defaultDifficulty(slotType: PracticeSlotType): 1 | 2 | 3 {
  if (slotType === 'song_section') return 3
  return 2
}

function normalizeDifficulty(value: unknown, slotType: PracticeSlotType): 1 | 2 | 3 {
  return value === 1 || value === 2 || value === 3 ? value : defaultDifficulty(slotType)
}

function normalizeIntent(value: unknown): PlanSlotIntent {
  return SLOT_INTENTS.includes(value as PlanSlotIntent) ? (value as PlanSlotIntent) : 'practice'
}

function normalizeSlot(raw: UnknownRecord, index: number): DrillSlotPayload {
  const slotType = SLOT_TYPES.includes(raw.slot_type as PracticeSlotType)
    ? (raw.slot_type as PracticeSlotType)
    : 'technique'
  const title = nonEmptyString(raw.title) ?? `Practice step ${index + 1}`
  return {
    ...(raw as unknown as DrillSlotPayload),
    slot_id: nonEmptyString(raw.slot_id) ?? createId(),
    slot_type: slotType,
    duration_seconds:
      typeof raw.duration_seconds === 'number' && Number.isFinite(raw.duration_seconds)
        ? Math.max(0, Math.round(raw.duration_seconds))
        : 0,
    title,
    coach_intro: typeof raw.coach_intro === 'string' ? raw.coach_intro : '',
    difficulty: normalizeDifficulty(raw.difficulty, slotType),
    intent: normalizeIntent(raw.intent),
    target_skill: nonEmptyString(raw.target_skill),
    remediation_for_slot_id: nonEmptyString(raw.remediation_for_slot_id),
  }
}

/** Fill IDs/defaults for backend, cached, and legacy plan payloads at entry boundaries. */
export function normalizePracticePlan(plan: PracticePlanPayload): PracticePlanPayload {
  const raw = plan as unknown as UnknownRecord
  const rawSlots = Array.isArray(raw.slots) ? (raw.slots as UnknownRecord[]) : []
  const slots = rawSlots.map((slot, index) => normalizeSlot(slot, index))
  return {
    ...(raw as unknown as PracticePlanPayload),
    plan_id: nonEmptyString(raw.plan_id) ?? createId(),
    slots,
    total_duration_seconds: slots.reduce((sum, slot) => sum + slot.duration_seconds, 0),
  }
}
