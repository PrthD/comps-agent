type Props = {
  state: 'checking' | 'warming'
  onRetry: () => void
}

export default function WarmingScreen({ state, onRetry }: Props) {
  const warming = state === 'warming'
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-6 py-24 text-center">
      <div className="mb-4 h-6 w-6 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-700" />
      <h2 className="text-sm font-semibold text-neutral-900">
        {warming ? 'Warming up the valuation engine' : 'Connecting to the valuation engine'}
      </h2>
      <p className="mt-1.5 text-xs leading-relaxed text-neutral-500">
        {warming
          ? 'The backend sleeps on the free tier and wakes in about 30 seconds. Retrying automatically.'
          : 'Checking the API health endpoint.'}
      </p>
      {warming && (
        <button
          onClick={onRetry}
          className="mt-4 rounded border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50"
        >
          Retry now
        </button>
      )}
    </div>
  )
}
