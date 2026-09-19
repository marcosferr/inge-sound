import { useCallback, useMemo, useState } from 'react'

import { Dropzone } from './components/Dropzone'
import { WaveIcon } from './components/Icons'
import { JobCard } from './components/JobCard'
import { OptionsPanel } from './components/OptionsPanel'
import { useCapabilities } from './hooks/useCapabilities'
import { useJobs } from './hooks/useJobs'
import { api } from './lib/api'
import type { Capabilities, JobStatus } from './lib/types'

const FILTERS: { key: JobStatus | 'all'; label: string }[] = [
  { key: 'all', label: 'Todos' },
  { key: 'running', label: 'En curso' },
  { key: 'completed', label: 'Listos' },
  { key: 'failed', label: 'Con error' },
]

export default function App() {
  const { capabilities, error: capabilitiesError, loading } = useCapabilities()
  const { jobs, cancel, retry, destroy, upsert } = useJobs()

  const [files, setFiles] = useState<File[]>([])
  const [options, setOptions] = useState<Record<string, unknown> | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [filter, setFilter] = useState<JobStatus | 'all'>('all')

  // Defaults come from the backend catalog, so the two never drift apart.
  const values = useMemo(() => {
    if (options) return options
    if (!capabilities) return {}
    return Object.fromEntries(
      capabilities.options.map((option) => [option.key, option.default]),
    )
  }, [options, capabilities])

  const submit = useCallback(async () => {
    if (!files.length) return
    setUploading(true)
    setUploadProgress(0)
    setSubmitError(null)
    try {
      const job = await api.createJob(files, values, setUploadProgress)
      upsert(job)
      setFiles([])
    } catch (err) {
      setSubmitError((err as Error).message)
    } finally {
      setUploading(false)
    }
  }, [files, values, upsert])

  const visibleJobs = useMemo(
    () =>
      filter === 'all'
        ? jobs
        : jobs.filter((job) =>
            filter === 'running' ? job.status === 'running' || job.status === 'queued' : job.status === filter,
          ),
    [jobs, filter],
  )

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Conectando con el servidor…
      </main>
    )
  }

  if (capabilitiesError || !capabilities) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="card max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold text-rose-300">No se pudo contactar la API</h1>
          <p className="mt-2 text-sm text-slate-400">{capabilitiesError}</p>
          <p className="mt-4 text-xs text-slate-500">
            Verificá que el backend esté corriendo y que <code className="font-mono">/api</code> sea
            accesible desde el navegador.
          </p>
        </div>
      </main>
    )
  }

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-8 sm:px-6">
      <Header capabilities={capabilities} />

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:items-start">
        <section className="card space-y-5 p-5 lg:sticky lg:top-8">
          <h2 className="text-base font-semibold text-slate-100">Nueva separación</h2>

          <Dropzone
            files={files}
            onChange={setFiles}
            accept={capabilities.allowed_extensions}
            maxFiles={capabilities.max_files_per_job}
            maxSizeMb={capabilities.max_upload_mb}
            disabled={uploading}
          />

          <OptionsPanel capabilities={capabilities} values={values} onChange={setOptions} />

          {submitError && (
            <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              {submitError}
            </p>
          )}

          <button
            type="button"
            onClick={() => void submit()}
            disabled={!files.length || uploading}
            className="btn-primary w-full !py-2.5"
          >
            {uploading
              ? `Subiendo… ${Math.round(uploadProgress * 100)}%`
              : `Separar ${files.length || ''} ${files.length === 1 ? 'pista' : 'pistas'}`.trim()}
          </button>
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-100">
              Trabajos <span className="text-slate-500">({jobs.length})</span>
            </h2>
            <div className="flex gap-1 rounded-xl border border-white/5 bg-ink-900/60 p-1">
              {FILTERS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setFilter(item.key)}
                  className={
                    filter === item.key
                      ? 'rounded-lg bg-accent/15 px-3 py-1 text-xs font-medium text-accent'
                      : 'rounded-lg px-3 py-1 text-xs text-slate-400 transition hover:text-slate-200'
                  }
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {visibleJobs.length === 0 ? (
            <div className="card p-10 text-center">
              <WaveIcon className="mx-auto h-8 w-8 text-slate-700" />
              <p className="mt-3 text-sm text-slate-400">
                {jobs.length === 0
                  ? 'Todavía no separaste ninguna pista.'
                  : 'No hay trabajos con este filtro.'}
              </p>
            </div>
          ) : (
            visibleJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onCancel={cancel}
                onRetry={retry}
                onDelete={destroy}
              />
            ))
          )}
        </section>
      </div>

      <footer className="mt-12 border-t border-white/5 pt-6 text-center text-xs text-slate-600">
        Los archivos se borran automáticamente a las {capabilities.retention_hours} horas. Inge
        Sound es un wrapper de{' '}
        <a
          className="text-slate-400 underline decoration-dotted underline-offset-2 hover:text-accent"
          href="https://github.com/adefossez/demucs"
          target="_blank"
          rel="noreferrer"
        >
          Demucs
        </a>
        , publicado bajo licencia MIT por Meta AI.
      </footer>
    </div>
  )
}

function Header({ capabilities }: { capabilities: Capabilities }) {
  const badges = [
    capabilities.gpu_name ?? 'CPU',
    capabilities.demucs_version ? `Demucs ${capabilities.demucs_version}` : 'Demucs no detectado',
    capabilities.queue_backend === 'celery' ? 'Cola distribuida' : 'Cola local',
    capabilities.ffmpeg_available ? 'ffmpeg' : 'sin ffmpeg',
  ]

  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-white">
          <WaveIcon className="h-6 w-6 text-accent" />
          Inge Sound
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Separá voces, batería, bajo y más con los modelos de Demucs.
        </p>
      </div>
      <ul className="flex flex-wrap gap-1.5">
        {badges.map((badge) => (
          <li key={badge} className="chip bg-white/5 text-slate-400">
            {badge}
          </li>
        ))}
      </ul>
    </header>
  )
}
