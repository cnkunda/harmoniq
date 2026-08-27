import { useCallback, useState, type DragEvent } from 'react'

import colors from '@/src/constants/colors'

export interface AudioDropzoneProps {
  onFile: (file: Blob) => void
  accept?: string
}

/**
 * Web-only drag-and-drop / click-to-pick zone. Bundled only for web (`*.web.tsx`).
 */
export function AudioDropzone({
  onFile,
  accept = '.mp3,.wav,.m4a,audio/*',
}: AudioDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) onFile(file as Blob)
    },
    [onFile],
  )

  const handleClick = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.onchange = (ev) => {
      const picked = (ev.target as HTMLInputElement).files?.[0]
      if (picked) onFile(picked as Blob)
    }
    input.click()
  }

  const border = isDragging ? colors.amber.accent : colors.amber.accent + '55'
  const bg = isDragging ? colors.amber.accent + '14' : colors.wood[800] + 'AA'
  const fg = isDragging ? colors.amber.light : colors.cream

  return (
    <div
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          handleClick()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={handleClick}
      style={{
        border: `2px dashed ${border}`,
        borderRadius: 16,
        padding: '40px 28px',
        minHeight: 132,
        textAlign: 'center',
        cursor: 'pointer',
        background: bg,
        transition: 'all 0.2s ease',
        color: fg,
        fontFamily: 'DMSans-Regular',
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      {isDragging
        ? 'Drop to upload'
        : 'Drag an audio file here, or click to browse (MP3, WAV, M4A)'}
    </div>
  )
}
