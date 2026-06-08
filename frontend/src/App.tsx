import { useCallback, useEffect, useRef, useState } from 'react'

import {
  fetchRationale,
  getHealth,
  valueSubject,
  type HealthStatus,
  type Subject,
  type Valuation,
} from './api'
import Header from './components/Header'
import InputPanel from './components/InputPanel'
import ResultsView from './components/ResultsView'
import WarmingScreen from './components/WarmingScreen'

const DEFAULT_AS_OF = '2015-05-01' // inside the dataset window; a current date returns zero comps

export function emptySubject(): Subject {
  return {
    property_type: 'detached',
    beds: null,
    baths: null,
    sqft_living: null,
    sqft_lot: null,
    year_built: null,
    condition: null,
    grade: null,
    lat: null,
    lng: null,
    as_of_date: DEFAULT_AS_OF,
    field_confidence: null,
    needs_review: null,
  }
}

type Health = 'checking' | 'warming' | 'ready'

export default function App() {
  const [health, setHealth] = useState<Health>('checking')
  const [healthInfo, setHealthInfo] = useState<HealthStatus | null>(null)
  const [subject, setSubject] = useState<Subject>(emptySubject)
  const [valuation, setValuation] = useState<Valuation | null>(null)
  const [missingFields, setMissingFields] = useState<string[]>([])
  const [valuing, setValuing] = useState(false)
  const [rationaleLoading, setRationaleLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Bumped on each value/reset so a late rationale response can't patch a newer valuation.
  const requestId = useRef(0)

  const checkHealth = useCallback(async () => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 4000)
    try {
      const info = await getHealth(controller.signal)
      setHealthInfo(info)
      setHealth('ready')
    } catch {
      setHealth('warming')
    } finally {
      clearTimeout(timeout)
    }
  }, [])

  useEffect(() => {
    checkHealth()
  }, [checkHealth])

  // While the engine is cold, keep retrying until it answers.
  useEffect(() => {
    if (health !== 'warming') return
    const id = setInterval(checkHealth, 5000)
    return () => clearInterval(id)
  }, [health, checkHealth])

  // Any subject change clears a prior gate result so stale highlights never linger.
  const updateSubject = useCallback((next: Subject) => {
    setSubject(next)
    setMissingFields([])
    setError(null)
  }, [])

  const handleValue = useCallback(async () => {
    const reqId = (requestId.current += 1)
    setValuing(true)
    setError(null)
    setMissingFields([])
    setRationaleLoading(false)
    try {
      const result = await valueSubject(subject)
      if (!result.ok) {
        setMissingFields(result.incomplete.missing_fields)
        return
      }
      // Phase 1: the deterministic value is back in ~100ms; render it immediately.
      setValuation(result.valuation)
      // Phase 2: stream the LLM rationale in if there's a model and a value to explain. The
      // headline, stat row, map, and table are already on screen; only the rationale panel waits.
      if (healthInfo?.model_available && result.valuation.point_estimate > 0) {
        setRationaleLoading(true)
        fetchRationale(subject)
          .then((r) => {
            if (requestId.current !== reqId) return // a newer valuation superseded this one
            setValuation((cur) => (cur ? { ...cur, rationale: r.rationale, mode: r.mode } : cur))
          })
          .catch(() => {}) // keep the deterministic template rationale on any failure
          .finally(() => {
            if (requestId.current === reqId) setRationaleLoading(false)
          })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Valuation request failed')
    } finally {
      setValuing(false)
    }
  }, [subject, healthInfo])

  const reset = useCallback(() => {
    requestId.current += 1 // cancel any in-flight rationale patch
    setValuation(null)
    setMissingFields([])
    setRationaleLoading(false)
    setError(null)
  }, [])

  return (
    <div className="flex min-h-full flex-col">
      <Header />
      <main className="flex-1">
        {health !== 'ready' ? (
          <WarmingScreen state={health} onRetry={checkHealth} />
        ) : valuation ? (
          <ResultsView
            valuation={valuation}
            subject={subject}
            onBack={reset}
            rationaleLoading={rationaleLoading}
          />
        ) : (
          <InputPanel
            subject={subject}
            onSubject={updateSubject}
            onValue={handleValue}
            valuing={valuing}
            missingFields={missingFields}
            error={error}
          />
        )}
      </main>
      <footer className="border-t border-neutral-200 bg-white px-4 py-3 text-center text-[11px] text-neutral-400">
        {healthInfo
          ? `${healthInfo.comps_loaded.toLocaleString()} King County sales,`
          : 'King County sales,'}{' '}
        2014 to 2015. The LLM normalizes and explains; every number is computed by a deterministic,
        tested engine.
      </footer>
    </div>
  )
}
