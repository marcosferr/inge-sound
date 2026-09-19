import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../lib/api'
import { isTerminal, type Job } from '../lib/types'

const POLL_MS = 2000

/**
 * Keeps the job list fresh.
 *
 * Unfinished jobs are followed over SSE (one stream each); polling only covers
 * the case where a job is created or removed by another tab.
 */
export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const streams = useRef(new Map<string, EventSource>())

  const upsert = useCallback((job: Job) => {
    setJobs((current) => {
      const index = current.findIndex((item) => item.id === job.id)
      if (index === -1) return [job, ...current]
      const next = [...current]
      next[index] = job
      return next
    })
  }, [])

  const remove = useCallback((id: string) => {
    setJobs((current) => current.filter((job) => job.id !== id))
  }, [])

  const refresh = useCallback(async () => {
    try {
      const list = await api.listJobs()
      setJobs(list.items)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), POLL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  // One SSE stream per in-flight job, closed as soon as it settles.
  useEffect(() => {
    const open = streams.current
    for (const job of jobs) {
      if (isTerminal(job) || open.has(job.id)) continue
      const source = new EventSource(api.eventsUrl(job.id))
      open.set(job.id, source)
      source.addEventListener('job', (event) => {
        upsert(JSON.parse((event as MessageEvent).data) as Job)
      })
      source.addEventListener('deleted', () => {
        remove(job.id)
        source.close()
        open.delete(job.id)
      })
      source.addEventListener('done', () => {
        source.close()
        open.delete(job.id)
      })
      source.onerror = () => {
        // The polling loop above is the fallback when SSE cannot connect.
        source.close()
        open.delete(job.id)
      }
    }
    for (const [id, source] of open) {
      const job = jobs.find((item) => item.id === id)
      if (!job || isTerminal(job)) {
        source.close()
        open.delete(id)
      }
    }
  }, [jobs, upsert, remove])

  useEffect(() => {
    const open = streams.current
    return () => {
      open.forEach((source) => source.close())
      open.clear()
    }
  }, [])

  const cancel = useCallback(
    async (id: string) => upsert(await api.cancelJob(id)),
    [upsert],
  )

  const retry = useCallback(
    async (id: string) => {
      const job = await api.retryJob(id)
      upsert(job)
      return job
    },
    [upsert],
  )

  const destroy = useCallback(
    async (id: string) => {
      await api.deleteJob(id)
      remove(id)
    },
    [remove],
  )

  return { jobs, error, refresh, upsert, cancel, retry, destroy }
}
