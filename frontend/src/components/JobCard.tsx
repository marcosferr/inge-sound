import clsx from 'clsx'
import { useState } from 'react'

import { api } from '../lib/api'
import { formatEta, formatRelativeTime } from '../lib/format'
import type { Job, JobStatus } from '../lib/types'
import { ChevronIcon, RetryIcon, StopIcon, TrashIcon } from './Icons'
import { StemPlayer } from './StemPlayer'

interface Props {
  job: Job
  onCancel: (id: string) => Promise<void>
  onRetry: (id: string) => Promise<unknown>
  onDelete: (id: string) => Promise<void>
}

const STATUS_STYLES: Record<JobStatus, { label: string; className: string }> = {
  queued: { label: 'En cola', className: 'bg-slate-500/15 text-slate-300' },
  running: { label: 'Procesando', className: 'bg-accent/15 text-accent' },
  completed: { label: 'Listo', className: 'bg-emerald-500/15 text-emerald-300' },
  failed: { label: 'Error', className: 'bg-rose-500/15 text-rose-300' },
  cancelled: { label: 'Cancelado', className: 'bg-amber-500/15 text-amber-300' },
}

export function JobCard({ job, onCancel, onRetry, onDelete }: Props) {
  const [showDetails, setShowDetails] = useState(false)
  const [log, setLog] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const status = STATUS_STYLES[job.status]
  const active = job.status === 'queued' || job.status === 'running'
  const title = job.tracks.map((track) => track.original_filename).join(', ') || job.id.slice(0, 8)

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await action()
    } finally {
      setBusy(false)
    }
  }

  const toggleDetails = async () => {
    const next = !showDetails
    setShowDetails(next)
    if (next && log === null) {
      try {
        setLog((await api.getLog(job.id)).log || '(sin salida)')
      } catch {
        setLog('(no se pudo leer el log)')
      }
    }
  }

  return (
    <article className="card overflow-hidden">
      <header className="flex flex-wrap items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={clsx('chip', status.className)}>{status.label}</span>
            <span className="text-xs text-slate-500">{formatRelativeTime(job.created_at)}</span>
          </div>
          <h3 className="mt-1.5 truncate text-sm font-medium text-slate-100" title={title}>
            {title}
          </h3>
          <p className="mt-0.5 font-mono text-[11px] text-slate-500">
            {String(job.options.model)}
            {job.options.two_stems ? ` · 2 pistas (${String(job.options.two_stems)})` : ''}
            {` · ${String(job.options.format).toUpperCase()}`}
            {Number(job.options.shifts) > 0 ? ` · ${String(job.options.shifts)} shifts` : ''}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          {active && (
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => onCancel(job.id))}
              className="btn-ghost !px-2.5 !py-1.5 text-xs"
              title="Cancelar"
            >
              <StopIcon className="h-3.5 w-3.5" />
            </button>
          )}
          {!active && (
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => onRetry(job.id))}
              className="btn-ghost !px-2.5 !py-1.5 text-xs"
              title="Volver a separar con las mismas opciones"
            >
              <RetryIcon className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => onDelete(job.id))}
            className="btn-danger !px-2.5 !py-1.5 text-xs"
            title="Eliminar"
          >
            <TrashIcon className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={toggleDetails}
            className="btn-ghost !px-2.5 !py-1.5 text-xs"
            title="Detalles y log"
            aria-expanded={showDetails}
          >
            <ChevronIcon className={clsx('h-3.5 w-3.5 transition', showDetails && 'rotate-180')} />
          </button>
        </div>
      </header>

      {active && (
        <div className="px-4 pb-4">
          <div className="mb-1.5 flex items-center justify-between text-xs text-slate-400">
            <span>
              {job.progress.stage === 'separating' && job.progress.current_track
                ? `Separando ${job.progress.current_track}`
                : 'Preparando…'}
              {job.progress.tracks_total > 1 &&
                ` · ${job.progress.tracks_done + 1}/${job.progress.tracks_total}`}
            </span>
            <span className="font-mono">
              {job.progress.percent.toFixed(0)}% {formatEta(job.progress.eta_seconds)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${Math.max(2, job.progress.percent)}%` }}
            />
          </div>
        </div>
      )}

      {job.error && (
        <p className="mx-4 mb-4 rounded-lg bg-rose-500/10 px-3 py-2 text-xs leading-relaxed text-rose-300">
          {job.error}
        </p>
      )}

      {job.status === 'completed' && job.stems.length > 0 && (
        <div className="border-t border-white/5 p-4">
          <StemPlayer job={job} />
        </div>
      )}

      {showDetails && (
        <div className="space-y-3 border-t border-white/5 bg-ink-950/50 p-4 text-xs">
          <div>
            <p className="mb-1 font-semibold uppercase tracking-wider text-slate-500">Comando</p>
            <code className="block overflow-x-auto whitespace-pre rounded-lg bg-black/40 p-2.5 font-mono text-[11px] text-slate-400">
              {job.command.join(' ') || '(todavía no se lanzó)'}
            </code>
          </div>
          <div>
            <p className="mb-1 font-semibold uppercase tracking-wider text-slate-500">Opciones</p>
            <code className="block overflow-x-auto rounded-lg bg-black/40 p-2.5 font-mono text-[11px] text-slate-400">
              {JSON.stringify(job.options, null, 1)}
            </code>
          </div>
          <div>
            <p className="mb-1 font-semibold uppercase tracking-wider text-slate-500">
              Log <span className="font-normal normal-case tracking-normal">(últimos 200 KB)</span>
            </p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-black/40 p-2.5 font-mono text-[11px] leading-relaxed text-slate-400">
              {log ?? 'Cargando…'}
            </pre>
          </div>
        </div>
      )}
    </article>
  )
}
