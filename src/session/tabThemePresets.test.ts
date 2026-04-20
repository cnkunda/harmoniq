import { describe, expect, it } from 'vitest'

import {
  DEFAULT_TAB_RENDER_PRESET,
  getTabRenderPreset,
  normalizeTabRenderPresetName,
  TAB_RENDER_PRESETS,
} from './tabThemePresets'

describe('tabThemePresets', () => {
  it('normalizes unknown names to study', () => {
    expect(normalizeTabRenderPresetName('')).toBe(DEFAULT_TAB_RENDER_PRESET)
    expect(normalizeTabRenderPresetName('bogus')).toBe(DEFAULT_TAB_RENDER_PRESET)
    expect(normalizeTabRenderPresetName('PLAY')).toBe('play')
  })

  it('slow preset uses larger scale than listen', () => {
    expect(TAB_RENDER_PRESETS.slow.scale).toBeGreaterThan(TAB_RENDER_PRESETS.listen.scale)
  })

  it('getTabRenderPreset returns study for garbage', () => {
    expect(getTabRenderPreset('nope').name).toBe('study')
  })
})
