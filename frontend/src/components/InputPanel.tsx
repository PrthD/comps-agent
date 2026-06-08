import { useState } from 'react'

import { extractSubject, type Sample, type Subject } from '../api'
import SampleMenu from './SampleMenu'
import SubjectForm from './SubjectForm'

type Tab = 'upload' | 'paste' | 'form'

const TABS: { id: Tab; label: string }[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'paste', label: 'Paste text' },
  { id: 'form', label: 'Fill form' },
]

type Props = {
  subject: Subject
  onSubject: (subject: Subject) => void
  onValue: () => void
  valuing: boolean
  missingFields: string[]
  error: string | null
}

export default function InputPanel({
  subject,
  onSubject,
  onValue,
  valuing,
  missingFields,
  error,
}: Props) {
  const [tab, setTab] = useState<Tab>('form')
  const [extracted, setExtracted] = useState(false)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)

  async function runExtract(input: { file?: File; text?: string }) {
    setExtracting(true)
    setExtractError(null)
    try {
      const result = await extractSubject(input)
      onSubject(result)
      setExtracted(true)
      setTab('form')
    } catch (e) {
      setExtractError(e instanceof Error ? e.message : 'Extraction failed')
    } finally {
      setExtracting(false)
    }
  }

  function loadSample(sample: Sample) {
    onSubject(sample.subject)
    setExtracted(false)
    setTab('form')
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-neutral-900">Value a property</h2>
        <span className="text-xs text-neutral-400">
          {tab === 'form'
            ? 'Enter property details to value.'
            : 'Extraction populates the form for review.'}
        </span>
      </div>

      <div className="overflow-hidden rounded-md border border-neutral-200 bg-white">
        <SampleMenu onPick={loadSample} />

        <div className="flex border-b border-neutral-200">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-xs font-medium transition ${
                tab === t.id
                  ? 'border-b-2 border-accent text-neutral-900'
                  : 'border-b-2 border-transparent text-neutral-500 hover:text-neutral-800'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {tab === 'upload' && (
            <div className="space-y-2.5">
              <input
                type="file"
                accept=".pdf,image/*"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-neutral-600 file:mr-3 file:rounded file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white hover:file:bg-accent-hover"
              />
              <p className="text-[11px] text-neutral-400">
                PDF or image of a property listing or appraisal. If extraction is unavailable, use
                Fill form to enter details manually.
              </p>
              <button
                onClick={() => file && runExtract({ file })}
                disabled={!file || extracting}
                className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-accent-hover disabled:opacity-60"
              >
                {extracting ? 'Extracting' : 'Extract fields'}
              </button>
              {extractError && <p className="text-xs text-red-700">{extractError}</p>}
            </div>
          )}

          {tab === 'paste' && (
            <div className="space-y-2.5">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={6}
                placeholder="Paste a property listing or description."
                className="w-full rounded border border-neutral-300 px-2.5 py-1.5 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-neutral-200"
              />
              <button
                onClick={() => text.trim() && runExtract({ text })}
                disabled={!text.trim() || extracting}
                className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-accent-hover disabled:opacity-60"
              >
                {extracting ? 'Extracting' : 'Extract fields'}
              </button>
              {extractError && <p className="text-xs text-red-700">{extractError}</p>}
            </div>
          )}

          {tab === 'form' && (
            <SubjectForm
              subject={subject}
              onChange={onSubject}
              onValue={onValue}
              valuing={valuing}
              missingFields={missingFields}
              error={error}
              extracted={extracted}
            />
          )}
        </div>
      </div>
    </div>
  )
}
