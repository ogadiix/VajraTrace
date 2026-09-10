export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r border-line bg-ink p-4 flex flex-col gap-2">
        <h2 className="text-lg font-bold text-trace-teal mb-4">VajraTrace</h2>
        <a href="/trace" className="px-3 py-2 rounded hover:bg-line/50 text-paper/80 hover:text-white transition">
          Trace
        </a>
        <a href="/analytics" className="px-3 py-2 rounded hover:bg-line/50 text-paper/80 hover:text-white transition">
          Analytics
        </a>
        <a href="/reports" className="px-3 py-2 rounded hover:bg-line/50 text-paper/80 hover:text-white transition">
          Reports
        </a>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6">
        {children}
      </main>
    </div>
  );
}
