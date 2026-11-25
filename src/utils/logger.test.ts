import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createLogger } from './logger'

const originalDev = (globalThis as { __DEV__?: boolean }).__DEV__

/** RN types declare `__DEV__` as a const global — redefine via the object. */
function setDev(value: boolean | undefined): void {
  Object.defineProperty(globalThis, '__DEV__', {
    value,
    writable: true,
    configurable: true,
    enumerable: true,
  })
}

describe('createLogger', () => {
  beforeEach(() => {
    vi.spyOn(console, 'debug').mockImplementation(() => {})
    vi.spyOn(console, 'info').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setDev(originalDev)
  })

  it('prefixes string messages and passes extra arguments through', () => {
    const log = createLogger('[Probe]')

    log.debug('booting', 7)
    log.info('ready')

    expect(vi.mocked(console.debug)).toHaveBeenCalledWith('[Probe] booting', 7)
    expect(vi.mocked(console.info)).toHaveBeenCalledWith('[Probe] ready')
  })

  it('always emits warn and error with the prefix', () => {
    const log = createLogger('[Probe]')

    log.warn('careful', 'x')
    log.error(new Error('boom'))

    expect(vi.mocked(console.warn)).toHaveBeenCalledWith('[Probe] careful', 'x')
    expect(vi.mocked(console.error)).toHaveBeenCalledWith('[Probe]', expect.any(Error))
  })

  it('suppresses debug and info when __DEV__ is false but still emits warn and error', () => {
    setDev(false)
    const log = createLogger('[Probe]')

    log.debug('hidden')
    log.info('hidden')
    log.warn('kept')
    log.error('kept')

    expect(vi.mocked(console.debug)).not.toHaveBeenCalled()
    expect(vi.mocked(console.info)).not.toHaveBeenCalled()
    expect(vi.mocked(console.warn)).toHaveBeenCalledWith('[Probe] kept')
    expect(vi.mocked(console.error)).toHaveBeenCalledWith('[Probe] kept')
  })

  it('treats an undefined __DEV__ as production — no emit, no throw', () => {
    setDev(undefined)
    const log = createLogger('[Probe]')

    expect(() => log.debug('gone')).not.toThrow()
    expect(() => log.info('gone')).not.toThrow()
    expect(vi.mocked(console.debug)).not.toHaveBeenCalled()
    expect(vi.mocked(console.info)).not.toHaveBeenCalled()
  })

  it('handles non-string leading arguments and empty calls', () => {
    const log = createLogger('[Probe]')
    const payload = { code: 7 }

    log.warn(payload)
    log.error()

    expect(vi.mocked(console.warn)).toHaveBeenCalledWith('[Probe]', payload)
    expect(vi.mocked(console.error)).toHaveBeenCalledWith('[Probe]')
  })
})
