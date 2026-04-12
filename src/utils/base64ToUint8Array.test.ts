import { describe, expect, it } from 'vitest'

import { JAM_REFERENCE_TAB_GP5_BASE64 } from '@/src/jam/jamReferenceTabGp5Base64'

import { base64ToUint8Array } from './base64ToUint8Array'

describe('base64ToUint8Array', () => {
  it('decodes jam reference GP5 same as Node Buffer (1322-byte canonical stub)', () => {
    const raw = JAM_REFERENCE_TAB_GP5_BASE64.replace(/\s/g, '')
    expect(raw.length % 4).toBe(0)
    const a = base64ToUint8Array(JAM_REFERENCE_TAB_GP5_BASE64)
    const b = Buffer.from(raw, 'base64')
    expect(a.length).toBe(1322)
    expect(b.length).toBe(1322)
    expect(Buffer.from(a).equals(b)).toBe(true)
  })

  it('decodes small vectors', () => {
    expect(base64ToUint8Array('').length).toBe(0)
    expect(Buffer.from(base64ToUint8Array('Zg==')).toString('utf8')).toBe('f')
    expect(Buffer.from(base64ToUint8Array('Zm8=')).toString('utf8')).toBe('fo')
    expect(Buffer.from(base64ToUint8Array('Zm9v')).toString('utf8')).toBe('foo')
  })
})
