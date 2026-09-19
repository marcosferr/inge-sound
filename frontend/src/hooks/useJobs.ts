import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../lib/api'
import type { Job } from '../lib/types'

const POLL_MS = 2000

/**
 * Browsers allow six concurrent HTTP/1.1 connections per origin. Each open SSE
 * stream holds one for as long as its job runs, so streaming every unfinished
 * job would starve the polling, the stem playback and the downloads. Queued
 * jobs barely change, so only the running ones get a stream and polling covers
 * the rest.
 */
const MAX_STREAMS = 3

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

  // One SSE stream per running job, capped, closed as soon as it settles.
  useEffect(() => {
    const open = streams.current
    const streamable = new Set(
      jobs.filter((job) => job.status === 'running').slice(0, MAX_STREAMS).map((job) => job.id),
    )
    for (const job of jobs) {
      if (!streamable.has(job.id) || open.has(job.id)) continue
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
      if (!streamable.has(id)) {
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
