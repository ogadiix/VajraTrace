export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight">
          <span className="text-trace-teal">Vajra</span>Trace
        </h1>
        <p className="text-lg text-paper/60 max-w-xl">
          Real-time identification of fraud-linked cryptocurrency exchanges
          through automated blockchain analytics.
        </p>
        <div className="flex gap-4 justify-center mt-8">
          <a
            href="/trace"
            className="px-6 py-3 bg-trace-teal text-white rounded-lg font-medium hover:bg-trace-teal/90 transition"
          >
            Start Tracing
          </a>
          <a
            href="/analytics"
            className="px-6 py-3 border border-line text-paper rounded-lg font-medium hover:bg-line/30 transition"
          >
            Dashboard
          </a>
        </div>
      </div>
    </main>
  );
}
