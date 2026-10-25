import { describe, expect, it } from 'vitest'

import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import {
  buildStemsExportUrl,
  canExportStems,
  exportableStemKeys,
  isExportableJobId,
  stemExportFilename,
  STEM_EXPORT_UNAVAILABLE_COPY,
} from './stemExport'

describe('buildStemsExportUrl', () => {
  it('builds the all-stems URL', () => {
    expect(buildStemsExportUrl('http://localhost:8000/', 'job-123')).toBe(
      'http://localhost:8000/jobs/job-123/stems',
    )
  })

  it('builds a single-stem URL and encodes values', () => {
    expect(buildStemsExportUrl('http://localhost:8000', 'job 123', 'guitar')).toBe(
      'http://localhost:8000/jobs/job%20123/stems?stem=guitar',
    )
  })
})

describe('stemExportFilename', () => {
  it('sanitizes the lesson title for the ZIP name', () => {
    expect(stemExportFilename('My Song / Take 2')).toBe('My Song _ Take 2-stems.zip')
  })

  it('falls back when the title is empty', () => {
    expect(stemExportFilename('   ')).toBe('harmoniq-stems.zip')
  })

  it('uses the stem name for single exports', () => {
    expect(stemExportFilename('ignored', 'bass')).toBe('bass.wav')
  })
})

describe('export eligibility', () => {
  it('rejects the demo lesson and empty ids', () => {
    expect(isExportableJobId(DEMO_LESSON_JOB_ID)).toBe(false)
    expect(isExportableJobId(null)).toBe(false)
    expect(isExportableJobId('')).toBe(false)
    expect(isExportableJobId('real-job')).toBe(true)
  })

  it('keeps only backend stem paths', () => {
    expect(
      exportableStemKeys({
        guitar: 'data/jobs/x/stems/guitar.wav',
        bass: 'bundled://demo/reggae-bass',
        drums: '   ',
      }),
    ).toEqual(['guitar'])
  })

  it('requires a real job and at least one backend stem', () => {
    expect(canExportStems('job-1', { guitar: 'data/jobs/1/stems/guitar.wav' })).toBe(true)
    expect(canExportStems(DEMO_LESSON_JOB_ID, { guitar: 'data/jobs/1/stems/guitar.wav' })).toBe(false)
    expect(canExportStems('job-1', { guitar: 'bundled://demo/reggae-guitar' })).toBe(false)
  })

  it('exposes a retention-friendly error message', () => {
    expect(STEM_EXPORT_UNAVAILABLE_COPY).toContain('no longer available')
  })
})
