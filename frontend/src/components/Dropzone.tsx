import clsx from 'clsx'
import { useCallback, useRef, useState } from 'react'

import { formatBytes } from '../lib/format'
import { TrashIcon, UploadIcon } from './Icons'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  accept: string[]
  maxFiles: number
  maxSizeMb: number
  disabled?: boolean
}

export function Dropzone({ files, onChange, accept, maxFiles, maxSizeMb, disabled }: Props) {
  const [dragging, setDragging] = useState(false)
  const [warning, setWarning] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const add = useCallback(
    (incoming: FileList | null) => {
      if (!incoming) return
      const accepted: File[] = []
      const rejected: string[] = []

      for (const file of Array.from(incoming)) {
        const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
        if (!accept.includes(extension)) {
          rejected.push(`${file.name} (formato no soportado)`)
        } else if (file.size > maxSizeMb * 1024 * 1024) {
          rejected.push(`${file.name} (supera ${maxSizeMb} MB)`)
        } else {
          accepted.push(file)
        }
      }

      const merged = [...files]
      for (const file of accepted) {
        const duplicate = merged.some(
          (existing) => existing.name === file.name && existing.size === file.size,
        )
        if (duplicate) continue
        if (merged.length >= maxFiles) {
          rejected.push(`${file.name} (máximo ${maxFiles} archivos)`)
          continue
        }
        merged.push(file)
      }

      setWarning(rejected.length ? rejected.join(' · ') : null)
      onChange(merged)
    },
    [accept, files, maxFiles, maxSizeMb, onChange],
  )

  const total = files.reduce((sum, file) => sum + file.size, 0)

  return (
    <div className="space-y-3">
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (!disabled) add(event.dataTransfer.files)
        }}
        className={clsx(
          'flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition',
          dragging
            ? 'border-accent bg-accent/5 text-accent'
            : 'border-white/10 text-slate-400 hover:border-white/25 hover:text-slate-200',
          disabled && 'pointer-events-none opacity-50',
        )}
      >
        <UploadIcon />
        <span className="text-sm font-medium text-slate-200">
          Arrastrá tus archivos o hacé clic para elegirlos
        </span>
        <span className="text-xs">
          Hasta {maxFiles} archivos · {maxSizeMb} MB c/u · {accept.slice(0, 6).join(' ')}
          {accept.length > 6 ? ' …' : ''}
        </span>
      </button>

      <input
        ref={input}
        type="file"
        multiple
        accept={accept.join(',')}
        className="hidden"
        onChange={(event) => {
          add(event.target.files)
          event.target.value = ''
        }}
      />

      {warning && (
        <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300">{warning}</p>
      )}

      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${file.size}-${index}`}
              className="flex items-center justify-between gap-3 rounded-lg bg-ink-800/70 px-3 py-2 text-sm"
            >
              <span className="truncate text-slate-200">{file.name}</span>
              <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
                {formatBytes(file.size)}
                <button
                  type="button"
                  aria-label={`Quitar ${file.name}`}
                  onClick={() => onChange(files.filter((_, i) => i !== index))}
                  className="text-slate-500 transition hover:text-rose-400"
                >
                  <TrashIcon className="h-3.5 w-3.5" />
                </button>
              </span>
            </li>
          ))}
          <li className="px-3 pt-1 text-xs text-slate-500">
            {files.length} archivo{files.length === 1 ? '' : 's'} · {formatBytes(total)}
          </li>
        </ul>
      )}
    </div>
  )
}
