/** Mirrors `backend/app/schemas.py`. */

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export type OptionType = 'enum' | 'int' | 'float' | 'bool' | 'string'

export interface OptionChoice {
  value: string | number | boolean
  label: string
}

/** One Demucs flag, as described by the backend catalog. */
export interface OptionSpec {
  key: string
  flag: string
  label: string
  help: string
  type: OptionType
  default: unknown
  choices: OptionChoice[]
  minimum: number | null
  maximum: number | null
  step: number | null
  group: string
  advanced: boolean
  depends_on: Record<string, unknown[]> | null
}

export interface ModelInfo {
  name: string
  label: string
  stems: string[]
  sub_models: number
  description: string
  quality: 'good' | 'better' | 'best'
  speed: 'fast' | 'medium' | 'slow' | 'very_slow'
  default: boolean
}

export interface Preset {
  key: string
  label: string
  description: string
  options: Record<string, unknown>
}

export interface Capabilities {
  demucs_version: string | null
  torch_version: string | null
  models: ModelInfo[]
  options: OptionSpec[]
  option_groups: { key: string; label: string }[]
  presets: Preset[]
  devices: string[]
  default_device: string
  gpu_name: string | null
  formats: string[]
  allowed_extensions: string[]
  max_upload_mb: number
  max_files_per_job: number
  retention_hours: number
  queue_backend: string
  ffmpeg_available: boolean
}

export interface StemFile {
  id: string
  track: string
  stem: string
  filename: string
  rel_path: string
  size_bytes: number
  format: string
}

export interface TrackInfo {
  name: string
  original_filename: string
  size_bytes: number
  duration_seconds: number | null
}

export interface JobProgress {
  percent: number
  stage: string
  current_track: string | null
  tracks_done: number
  tracks_total: number
  eta_seconds: number | null
}

export interface Job {
  id: string
  status: JobStatus
  options: Record<string, unknown>
  tracks: TrackInfo[]
  stems: StemFile[]
  progress: JobProgress
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  expires_at: string | null
  command: string[]
  pid: number | null
}

export interface JobList {
  items: Job[]
  total: number
  limit: number
  offset: number
}

export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'cancelled']

export function isTerminal(job: Job): boolean {
  return TERMINAL_STATUSES.includes(job.status)
}
