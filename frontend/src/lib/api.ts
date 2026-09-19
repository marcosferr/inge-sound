import type { Capabilities, Job, JobList, JobStatus, StemFile } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** FastAPI puts the message in `detail`, which may itself be a list of errors. */
async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          typeof item === 'string' ? item : `${item.field ?? ''} ${item.message ?? ''}`.trim(),
        )
        .join(' · ')
    }
    return JSON.stringify(body)
  } catch {
    return `${response.status} ${response.statusText}`
  }
}

export const api = {
  capabilities: () => request<Capabilities>('/capabilities'),

  listJobs: (status?: JobStatus) =>
    request<JobList>(`/jobs${status ? `?status=${status}` : ''}`),

  getJob: (id: string) => request<Job>(`/jobs/${id}`),

  getLog: (id: string) => request<{ log: string }>(`/jobs/${id}/log`),

  cancelJob: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: 'POST' }),

  retryJob: (id: string) => request<Job>(`/jobs/${id}/retry`, { method: 'POST' }),

  deleteJob: (id: string) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),

  /** Upload with progress, which `fetch` cannot report. */
  createJob(
    files: File[],
    options: Record<string, unknown>,
    onUploadProgress?: (fraction: number) => void,
  ): Promise<Job> {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    form.append('options', JSON.stringify(options))

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/jobs`)
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) onUploadProgress?.(event.loaded / event.total)
      })
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText) as Job)
        } else {
          let message = `${xhr.status} ${xhr.statusText}`
          try {
            const detail = JSON.parse(xhr.responseText)?.detail
            if (typeof detail === 'string') message = detail
            else if (Array.isArray(detail)) {
              message = detail
                .map((item) => (typeof item === 'string' ? item : item.message))
                .join(' · ')
            }
          } catch {
            /* keep the status line */
          }
          reject(new ApiError(message, xhr.status))
        }
      })
      xhr.addEventListener('error', () => reject(new ApiError('Fallo de red', 0)))
      xhr.send(form)
    })
  },

  stemUrl: (jobId: string, stem: StemFile) => `${BASE}/jobs/${jobId}/stems/${stem.id}`,
  stemDownloadUrl: (jobId: string, stem: StemFile) =>
    `${BASE}/jobs/${jobId}/stems/${stem.id}/download`,
  zipUrl: (jobId: string) => `${BASE}/jobs/${jobId}/download`,
  eventsUrl: (jobId: string) => `${BASE}/jobs/${jobId}/events`,
}
