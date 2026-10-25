import { Buffer } from 'buffer'
import * as FileSystem from 'expo-file-system/legacy'
import * as Sharing from 'expo-sharing'
import { Platform } from 'react-native'

function parseContentDispositionFilename(header: string | null): string | null {
  if (!header?.trim()) return null
  const star = /filename\*=UTF-8''([^;\s]+)/i.exec(header)
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].replace(/(^")|("$)/g, '').trim())
    } catch {
      return star[1].trim()
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(header)
  if (quoted?.[1]) return quoted[1]
  const plain = /filename=([^;\s]+)/i.exec(header)
  return plain?.[1] ?? null
}

function extFromMime(mimeType: string): string {
  const m = mimeType.toLowerCase()
  if (m.includes('musicxml')) return '.musicxml'
  if (m.includes('midi')) return '.mid'
  if (m.includes('zip')) return '.zip'
  if (m.includes('wav')) return '.wav'
  return ''
}

/**
 * Save a downloaded export blob — share sheet on native, `<a download>` on web.
 */
export async function shareExportedBlob(params: {
  blob: Blob
  mimeType: string
  contentDisposition: string | null
  fallbackBase: string
  dialogTitle: string
}): Promise<void> {
  const { blob, mimeType, contentDisposition, fallbackBase, dialogTitle } = params
  const fromHeader = parseContentDispositionFilename(contentDisposition)?.trim()
  const ext = extFromMime(mimeType)
  const base = fallbackBase.replace(/[^\w.\-()+ ]+/g, '_').slice(0, 80) || 'harmoniq-export'
  const filename =
    fromHeader && fromHeader.includes('.')
      ? fromHeader
      : fromHeader
        ? `${fromHeader}${ext}`
        : `${base}${ext}`

  if (Platform.OS === 'web') {
    if (typeof document === 'undefined') throw new Error('Web export requires a document')
    const url = URL.createObjectURL(blob)
    try {
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.rel = 'noopener'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      URL.revokeObjectURL(url)
    }
    return
  }

  const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
  if (!dir) throw new Error('No writable directory for export')
  const safeName = filename.replace(/[^\w.\-()+ ]+/g, '_')
  const path = `${dir}${safeName}`
  const b64 = Buffer.from(await blob.arrayBuffer()).toString('base64')
  await FileSystem.writeAsStringAsync(path, b64, { encoding: FileSystem.EncodingType.Base64 })
  const canShare = await Sharing.isAvailableAsync()
  if (!canShare) throw new Error('Share sheet unavailable on this device')
  await Sharing.shareAsync(path, { mimeType, dialogTitle })
}

async function readDownloadErrorDetail(uri: string, status: number): Promise<string> {
  try {
    const body = await FileSystem.readAsStringAsync(uri)
    const parsed = JSON.parse(body) as { detail?: unknown }
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) return parsed.detail
  } catch (e) {
    console.warn('[exportShare] could not read export error body', e)
  }
  return `Export failed (HTTP ${status}).`
}

/**
 * Download an export URL straight to the native cache and open the share sheet.
 * Avoids buffering large exports (e.g. stem ZIPs) in JS memory.
 */
export async function downloadAndShareExport(params: {
  url: string
  filename: string
  mimeType: string
  dialogTitle: string
}): Promise<void> {
  if (Platform.OS === 'web') throw new Error('Use shareExportedBlob for web exports')
  const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
  if (!dir) throw new Error('No writable directory for export')
  const safeName = params.filename.replace(/[^\w.\-()+ ]+/g, '_')
  const path = `${dir}${safeName}`
  const result = await FileSystem.downloadAsync(params.url, path)
  if (result.status < 200 || result.status >= 300) {
    const detail = await readDownloadErrorDetail(result.uri, result.status)
    await FileSystem.deleteAsync(result.uri, { idempotent: true }).catch((e) => {
      console.warn('[exportShare] could not remove failed export file', e)
    })
    throw new Error(detail)
  }
  const canShare = await Sharing.isAvailableAsync()
  if (!canShare) throw new Error('Share sheet unavailable on this device')
  await Sharing.shareAsync(path, { mimeType: params.mimeType, dialogTitle: params.dialogTitle })
}
