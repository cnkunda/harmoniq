import { create } from 'zustand'

import {
  RUNTIME_DIAG_THRESHOLDS,
} from '@/src/constants/alphaTabRuntimeDiag'

export type AlphaTabRuntimeDiagSource = 'harness' | 'web-dom'

export type AlphaTabRuntimeDiagSnapshot = {
  driftMs: number | null
  noteEventHz: number | null
  renderFps: number | null
  bridgeLatencyMs: number | null
  breachFlags: readonly string[]
  windowMs: number
  updatedAt: number
  source: AlphaTabRuntimeDiagSource
}

type State = {
  latest: AlphaTabRuntimeDiagSnapshot | null
  ingestHarnessWindow: (payload: {
    windowMs: number
    driftMs: number | null
    noteEventHz: number
    renderFps: number
    breachFlags?: readonly string[]
    source: AlphaTabRuntimeDiagSource
  }) => void
  setBridgeLatencyMs: (ms: number | null) => void
  clear: () => void
}

function mergeBreaches(
  harness: readonly string[],
  bridgeMs: number | null,
): readonly string[] {
  const out = harness.filter((b) => b !== 'BRIDGE_MS')
  if (bridgeMs != null && bridgeMs > RUNTIME_DIAG_THRESHOLDS.bridgeLatencyMsFail) {
    out.push('BRIDGE_MS')
  }
  return out
}

export const useAlphaTabRuntimeDiagStore = create<State>((set, get) => ({
  latest: null,

  ingestHarnessWindow: (payload) => {
    const now = Date.now()
    const bridge = get().latest?.bridgeLatencyMs ?? null
    const breachFlags = mergeBreaches(payload.breachFlags ?? [], bridge)
    set({
      latest: {
        driftMs: payload.driftMs,
        noteEventHz: payload.noteEventHz,
        renderFps: payload.renderFps,
        bridgeLatencyMs: bridge,
        breachFlags,
        windowMs: payload.windowMs,
        updatedAt: now,
        source: payload.source,
      },
    })
  },

  setBridgeLatencyMs: (ms) => {
    const prev = get().latest
    const breachFlags = mergeBreaches(prev?.breachFlags ?? [], ms)
    set({
      latest:
        prev != null
          ? {
              ...prev,
              bridgeLatencyMs: ms,
              breachFlags,
              updatedAt: Date.now(),
            }
          : {
              driftMs: null,
              noteEventHz: null,
              renderFps: null,
              bridgeLatencyMs: ms,
              breachFlags,
              windowMs: 0,
              updatedAt: Date.now(),
              source: 'harness',
            },
    })
  },

  clear: () => set({ latest: null }),
}))
