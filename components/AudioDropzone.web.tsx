import { Upload } from 'lucide-react-native'
import { useCallback, useState, type DragEvent } from 'react'
import { View } from 'react-native'

import { colors } from '@/src/constants/colors'

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

  const border = isDragging ? colors.amber.accent : colors.wood[600]
  const bg = isDragging ? colors.amber.accent + '20' : colors.wood[800] + '80'
  const fg = isDragging ? colors.amber.light : colors.cream
  const iconColor = isDragging ? colors.amber.light : colors.amber.accent

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
        border: `2px ${isDragging ? 'solid' : 'dashed'} ${border}`,
        borderRadius: 16,
        padding: '36px 28px',
        minHeight: 132,
        textAlign: 'center',
        cursor: 'pointer',
        background: bg,
        transition: 'border 0.25s ease, background 0.25s ease, box-shadow 0.25s ease',
        color: fg,
        fontFamily: 'DMSans-Regular',
        fontSize: 14,
        lineHeight: 1.5,
        boxShadow: isDragging
          ? `0 0 0 3px ${colors.amber.accent}30, inset 0 0 20px ${colors.amber.accent}10`
          : 'none',
      }}
    >
      <View className="items-center gap-3">
        <Upload size={32} color={iconColor} strokeWidth={1.5} />
        <span>
          {isDragging
            ? 'Drop to upload'
            : 'Drag an audio file here, or click to browse (MP3, WAV, M4A)'}
        </span>
      </View>
    </div>
  )
}
