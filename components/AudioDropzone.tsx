import type { ReactNode } from 'react'

/** Native / non-web: drag-drop is web-only; use document picker on native instead. */
export interface AudioDropzoneProps {
  onFile: (file: Blob) => void
  accept?: string
}

export function AudioDropzone(_props: AudioDropzoneProps): ReactNode {
  return null
}
