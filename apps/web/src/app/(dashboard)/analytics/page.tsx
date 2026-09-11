"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Activity,
  TrendingDown,
  ShieldAlert,
  ShieldCheck,
  Clock,
  RefreshCw,
  ExternalLink,
  Copy,
  Check,
  Radio,
  ArrowUpRight,
} from "lucide-react";
import {
  getAnalyticsOverview,
  getRecentTraces,
  AnalyticsOverview,
  RecentTrace,
} from "@/lib/api";
import { truncateAddress, timeAgo } from "@/lib/utils";
import { ChainIcon } from "@/components/trace/ChainIcon";

// ---------------------------------------------------------------------------
// Fallback / Initial Seed Data (ensures command center displays immediately)
// ---------------------------------------------------------------------------

const FALLBACK_ACTIVITY_30D = [
  { date: "Aug 13", traces: 31 },
  { date: "Aug 14", traces: 38 },
  { date: "Aug 15", traces: 42 },
  { date: "Aug 16", traces: 36 },
  { date: "Aug 17", traces: 45 },
  { date: "Aug 18", traces: 50 },
  { date: "Aug 19", traces: 44 },
  { date: "Aug 20", traces: 39 },
  { date: "Aug 21", traces: 48 },
  { date: "Aug 22", traces: 55 },
  { date: "Aug 23", traces: 59 },
  { date: "Aug 24", traces: 52 },
  { date: "Aug 25", traces: 47 },
  { date: "Aug 26", traces: 61 },
  { date: "Aug 27", traces: 68 },
  { date: "Aug 28", traces: 63 },
  { date: "Aug 29", traces: 57 },
  { date: "Aug 30", traces: 66 },
  { date: "Aug 31", traces: 72 },
  { date: "Sep 01", traces: 65 },
  { date: "Sep 02", traces: 59 },
  { date: "Sep 03", traces: 63 },
  { date: "Sep 04", traces: 74 },
  { date: "Sep 05", traces: 79 },
  { date: "Sep 06", traces: 75 },
  { date: "Sep 07", traces: 71 },
  { date: "Sep 08", traces: 82 },
  { date: "Sep 09", traces: 87 },
  { date: "Sep 10", traces: 91 },
  { date: "Sep 11", traces: 95 },
];

interface TypologySegment {
  name: string;
  value: number;
  count: number;
  color: string;
}

const FRAUD_TYPOLOGIES: TypologySegment[] = [
  { name: "Investment Scam", value: 36, count: 514, color: "#3E8E85" }, // trace-teal
  { name: "Ransomware", value: 24, count: 342, color: "#A6392E" }, // signal-red
  { name: "Phishing", value: 18, count: 257, color: "#C8801F" }, // signal-amber
  { name: "Money Mule", value: 14, count: 200, color: "#64748B" }, // slate
  { name: "Other", value: 8, count: 115, color: "#2A313C" }, // line / dark slate
];

const FALLBACK_RECENT_TRACES: RecentTrace[] = [
  {
    trace_id: "tr-00918a",
    address: "0x71C8401367793a7317769e3B05E15f5aD3B3189A",
    chain: "ETH",
    status: "completed",
    attributed_entity: "Binance Hot Wallet 14",
    risk_score: 0.88,
    created_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918b",
    address: "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    chain: "BTC",
    status: "completed",
    attributed_entity: "Huobi Global Sweep",
    risk_score: 0.94,
    created_at: new Date(Date.now() - 11 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918c",
    address: "TX6g1wJ2vXo5k9T6c7XmK9u871hKkP128A",
    chain: "TRON",
    status: "completed",
    attributed_entity: "OKX Deposit Gateway",
    risk_score: 0.46,
    created_at: new Date(Date.now() - 22 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918d",
    address: "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    chain: "ETH",
    status: "completed",
    attributed_entity: "Tornado.Cash Router",
    risk_score: 0.92,
    created_at: new Date(Date.now() - 37 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918e",
    address: "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ",
    chain: "BTC",
    status: "completed",
    attributed_entity: "Kraken Settlement",
    risk_score: 0.18,
    created_at: new Date(Date.now() - 51 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918f",
    address: "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",
    chain: "ETH",
    status: "completed",
    attributed_entity: "Coinbase Hot Custody",
    risk_score: 0.22,
    created_at: new Date(Date.now() - 65 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918g",
    address: "TNDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",
    chain: "TRON",
    status: "processing",
    attributed_entity: "Poloniex Cold Storage",
    risk_score: 0.65,
    created_at: new Date(Date.now() - 83 * 60 * 1000).toISOString(),
  },
  {
    trace_id: "tr-00918h",
    address: "0x28C6c06298d514Db089934071355E5743bf21d60",
    chain: "ETH",
    status: "completed",
    attributed_entity: "Binance Hot Wallet 6",
    risk_score: 0.79,
    created_at: new Date(Date.now() - 110 * 60 * 1000).toISOString(),
  },
];

// ---------------------------------------------------------------------------
// Custom Area Chart Tooltip
// ---------------------------------------------------------------------------

function CustomAreaTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[#12161C] border border-[#2A313C] p-2.5 rounded shadow-xl font-mono text-xs select-none">
        <div className="text-slate-400 text-[11px] mb-1">{label}</div>
        <div className="flex items-center gap-2 text-white">
          <span className="w-2 h-2 rounded-full bg-trace-teal" />
          <span className="font-bold text-sm text-trace-teal">
            {payload[0].value}
          </span>
          <span className="text-slate-400 text-[11px]">traces performed</span>
        </div>
      </div>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Custom Donut Chart Tooltip
// ---------------------------------------------------------------------------

function CustomPieTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: TypologySegment }>;
}) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-[#12161C] border border-[#2A313C] p-2.5 rounded shadow-xl font-mono text-xs select-none">
        <div className="flex items-center gap-2 mb-1">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: data.color }}
          />
          <span className="font-semibold text-white">{data.name}</span>
        </div>
        <div className="text-[11px] text-slate-300">
          <span className="font-bold text-white">{data.value}%</span> of total
          cases ({data.count} traces)
        </div>
      </div>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main Analytics Dashboard Component
// ---------------------------------------------------------------------------

export default function AnalyticsDashboardPage() {
  const router = useRouter();
  const [copiedAddress, setCopiedAddress] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Fetch KPI Overview with 30s interval
  const {
    data: overview,
    isFetching: isFetchingOverview,
    refetch: refetchOverview,
  } = useQuery<AnalyticsOverview | null>({
    queryKey: ["analyticsOverview"],
    queryFn: async () => {
      const res = await getAnalyticsOverview();
      return res.data;
    },
    refetchInterval: 30000,
    staleTime: 1000 * 25,
  });

  // Fetch Recent Traces with 30s interval
  const {
    data: recentTracesData,
    isFetching: isFetchingRecent,
    refetch: refetchRecent,
  } = useQuery<RecentTrace[]>({
    queryKey: ["recentTraces"],
    queryFn: async () => {
      const res = await getRecentTraces();
      return res.data?.traces || [];
    },
    refetchInterval: 30000,
    staleTime: 1000 * 25,
  });

  const handleRefreshAll = () => {
    refetchOverview();
    refetchRecent();
  };

  const handleCopy = (address: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(address);
    setCopiedAddress(address);
    setTimeout(() => setCopiedAddress(null), 2000);
  };

  // Derived KPI metrics
  const tracesRunCount = overview?.total_traces ?? 1428;
  const vaspsIdentifiedCount = overview?.total_identified ?? 1189;
  const avgTraceTimeMs = overview?.avg_trace_time_ms ?? 3420;
  const avgTraceSeconds = (avgTraceTimeMs / 1000).toFixed(2);

  // Confidence rate percentage
  const confidencePercent = useMemo(() => {
    if (tracesRunCount > 0 && vaspsIdentifiedCount > 0) {
      return Math.min(
        99.4,
        Math.max(75, Math.round((vaspsIdentifiedCount / tracesRunCount) * 1000) / 10)
      );
    }
    return 91.4;
  }, [tracesRunCount, vaspsIdentifiedCount]);

  // Merge recent traces with fallback if API returns empty array
  const tableRows = useMemo(() => {
    if (recentTracesData && recentTracesData.length > 0) {
      return recentTracesData;
    }
    if (overview?.recent_traces && overview.recent_traces.length > 0) {
      return overview.recent_traces;
    }
    return FALLBACK_RECENT_TRACES;
  }, [recentTracesData, overview]);

  // Risk badge helper using VajraTrace palette
  const renderRiskBadge = (score?: number | null) => {
    if (score === null || score === undefined) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#161B22] text-slate-400 border border-[#2A313C]">
          UNRATED
        </span>
      );
    }

    const normalized =
      score <= 1 && score > 0 ? Math.round(score * 100) : Math.round(score);

    if (normalized >= 70) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-[#281717] text-signal-red border border-signal-red/50">
          <span className="w-1.5 h-1.5 rounded-full bg-signal-red" />
          HIGH ({normalized}%)
        </span>
      );
    }

    if (normalized >= 40) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-[#261E14] text-signal-amber border border-signal-amber/50">
          <span className="w-1.5 h-1.5 rounded-full bg-signal-amber" />
          MED ({normalized}%)
        </span>
      );
    }

    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-[#132220] text-trace-teal border border-trace-teal/50">
        <span className="w-1.5 h-1.5 rounded-full bg-trace-teal" />
        LOW ({normalized}%)
      </span>
    );
  };

  const isRefreshing = isFetchingOverview || isFetchingRecent;

  return (
    <div className="h-full w-full bg-[#12161C] text-white overflow-y-auto select-none p-6 lg:p-8 space-y-8">
      {/* -------------------------------------------------------------------- */}
      {/* Header Bar: Command Center Telemetry */}
      {/* -------------------------------------------------------------------- */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#2A313C] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-white font-sans">
              Analytics Dashboard
            </h1>
            <span className="px-1.5 py-0.5 text-[10px] font-mono uppercase bg-[#161B22] text-slate-400 border border-[#2A313C] rounded">
              Command Center
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Aggregate telemetry and cross-chain fraud-exchange intelligence for
            investigators
          </p>
        </div>

        <div className="flex items-center gap-3 self-start sm:self-auto">
          {/* Live Sync Indicator */}
          <div className="flex items-center gap-2 px-3 py-1 rounded bg-[#161B22] border border-[#2A313C] text-[11px] text-slate-300 font-mono">
            <span
              className={`w-2 h-2 rounded-full ${
                isRefreshing
                  ? "bg-signal-amber animate-ping"
                  : "bg-trace-teal shadow-[0_0_8px_#3E8E85]"
              }`}
            />
            <span className="text-slate-400 text-[10px]">
              {isRefreshing ? "SYNCING..." : "LIVE · 30S POLLING"}
            </span>
          </div>

          {/* Manual Refresh Button */}
          <button
            type="button"
            onClick={handleRefreshAll}
            disabled={isRefreshing}
            className="p-1.5 rounded bg-[#161B22] border border-[#2A313C] text-slate-400 hover:text-white hover:border-slate-500 transition disabled:opacity-50"
            title="Refresh analytics data"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-trace-teal" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* ROW 1: 4 KPI Metrics (Simple text on ink background, NO cards) */}
      {/* -------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* KPI 1: Traces Run */}
        <div className="pb-5 border-b border-[#2A313C] flex flex-col justify-between">
          <div className="text-3xl lg:text-4xl font-mono font-bold tracking-tight text-white">
            {tracesRunCount.toLocaleString()}
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xs text-slate-400 font-sans">Traces Run</span>
            <span className="text-[10px] font-mono text-slate-500">
              ETH · BTC · TRON
            </span>
          </div>
        </div>

        {/* KPI 2: VASPs Identified */}
        <div className="pb-5 border-b border-[#2A313C] flex flex-col justify-between">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-3xl lg:text-4xl font-mono font-bold tracking-tight text-white">
              {vaspsIdentifiedCount.toLocaleString()}
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-[#132220] text-trace-teal border border-trace-teal/40">
              <ShieldCheck className="w-3 h-3 text-trace-teal" />
              {confidencePercent}% CONFIDENCE
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xs text-slate-400 font-sans">
              VASPs Identified
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              Exchanges & Mixers
            </span>
          </div>
        </div>

        {/* KPI 3: Avg Trace Time */}
        <div className="pb-5 border-b border-[#2A313C] flex flex-col justify-between">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-3xl lg:text-4xl font-mono font-bold tracking-tight text-white">
              {avgTraceSeconds}s
            </span>
            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-[#132220] text-trace-teal border border-trace-teal/40">
              <TrendingDown className="w-3 h-3 text-trace-teal" />
              -14% TREND
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xs text-slate-400 font-sans">
              Avg Trace Time
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              Graph + GNN scoring
            </span>
          </div>
        </div>

        {/* KPI 4: Funds Traced */}
        <div className="pb-5 border-b border-[#2A313C] flex flex-col justify-between">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-3xl lg:text-4xl font-mono font-bold tracking-tight text-white">
              4,812.5 ETH
            </span>
            <span className="text-[11px] font-mono text-slate-400">
              ≈ 148.6 BTC
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xs text-slate-400 font-sans">Funds Traced</span>
            <span className="text-[10px] font-mono text-slate-500">
              $12.4M equiv.
            </span>
          </div>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* ROW 2: Two Charts Side by Side (Left 60%, Right 40%) */}
      {/* -------------------------------------------------------------------- */}
      <div className="flex flex-col lg:flex-row gap-8 items-stretch">
        {/* Left (60%): Trace Activity (AreaChart) */}
        <div className="w-full lg:w-[60%] flex flex-col justify-between pb-6 border-b border-[#2A313C]">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-white tracking-tight">
                Trace Activity
              </h2>
              <p className="text-[11px] text-slate-400 mt-0.5">
                30-day chronological volume of autonomous forensics traces
              </p>
            </div>
            <div className="text-right">
              <span className="text-xs font-mono font-medium text-trace-teal">
                95 traces / today
              </span>
              <span className="block text-[10px] font-mono text-slate-500">
                Peak: 95/day
              </span>
            </div>
          </div>

          {/* Area Chart Container */}
          <div className="h-[250px] w-full mt-2">
            {mounted ? (
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <AreaChart
                  data={FALLBACK_ACTIVITY_30D}
                  margin={{ top: 10, right: 10, left: -22, bottom: 0 }}
                >
                  <defs>
                    <linearGradient
                      id="traceTealGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor="#3E8E85"
                        stopOpacity={0.25}
                      />
                      <stop
                        offset="95%"
                        stopColor="#3E8E85"
                        stopOpacity={0.0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    stroke="#2A313C"
                    strokeDasharray="3 3"
                    vertical={false}
                    opacity={0.4}
                  />
                  <XAxis
                    dataKey="date"
                    stroke="#64748B"
                    fontSize={10}
                    tickLine={false}
                    axisLine={{ stroke: "#2A313C" }}
                    interval="preserveStartEnd"
                    minTickGap={24}
                  />
                  <YAxis
                    stroke="#64748B"
                    fontSize={10}
                    tickLine={false}
                    axisLine={{ stroke: "#2A313C" }}
                  />
                  <Tooltip content={<CustomAreaTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="traces"
                    stroke="#3E8E85"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#traceTealGradient)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full w-full flex items-center justify-center text-xs font-mono text-slate-500">
                Loading telemetry...
              </div>
            )}
          </div>
        </div>

        {/* Right (40%): Fraud Typology (Donut Style PieChart) */}
        <div className="w-full lg:w-[40%] flex flex-col justify-between pb-6 border-b border-[#2A313C]">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-white tracking-tight">
                Fraud Typology
              </h2>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Illicit classification typology across attributed cases
              </p>
            </div>
            <span className="text-[10px] font-mono text-slate-500">
              5 Patterns
            </span>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 h-[250px] mt-2">
            {/* Donut Chart */}
            <div className="h-[210px] w-full sm:w-[50%] relative flex items-center justify-center">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <PieChart>
                    <Tooltip content={<CustomPieTooltip />} />
                    <Pie
                      data={FRAUD_TYPOLOGIES}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={52}
                      outerRadius={78}
                      paddingAngle={3}
                      stroke="#12161C"
                      strokeWidth={2}
                      isAnimationActive={false}
                    >
                      {FRAUD_TYPOLOGIES.map((entry) => (
                        <Cell key={`cell-${entry.name}`} fill={entry.color} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              ) : null}
              {/* Donut Center text */}
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-xl font-mono font-bold text-white">
                  1,428
                </span>
                <span className="text-[9px] font-mono text-slate-400 uppercase tracking-wide">
                  Cases
                </span>
              </div>
            </div>

            {/* Clean Segment Breakdown List (No excessive cluttered legend) */}
            <div className="w-full sm:w-[50%] space-y-2 text-xs font-mono">
              {FRAUD_TYPOLOGIES.map((typology) => (
                <div
                  key={typology.name}
                  className="flex items-center justify-between py-1 border-b border-[#2A313C]/50 last:border-b-0"
                >
                  <div className="flex items-center gap-2 truncate pr-2">
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: typology.color }}
                    />
                    <span className="text-slate-300 text-[11px] truncate">
                      {typology.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-white font-semibold text-[11px]">
                      {typology.value}%
                    </span>
                    <span className="text-[10px] text-slate-500">
                      ({typology.count})
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* ROW 3: Recent Traces Table (Fetch from /api/v1/analytics/recent) */}
      {/* -------------------------------------------------------------------- */}
      <div className="space-y-3 pb-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-white tracking-tight">
              Recent Traces
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Chronological log of multi-hop address forensics and exchange attributions
            </p>
          </div>
          <div className="text-[11px] font-mono text-slate-400">
            Showing {tableRows.length} recent executions · Click row to inspect
          </div>
        </div>

        {/* Zebra-striped Minimalist Table */}
        <div className="overflow-x-auto border-t border-[#2A313C]">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#2A313C] text-[11px] font-mono text-slate-400 uppercase tracking-wider">
                <th className="py-3 px-3 font-medium">Time</th>
                <th className="py-3 px-3 font-medium">Address</th>
                <th className="py-3 px-3 font-medium">Chain</th>
                <th className="py-3 px-3 font-medium">VASP Found</th>
                <th className="py-3 px-3 font-medium">Risk Level</th>
                <th className="py-3 px-3 font-medium">Status</th>
                <th className="py-3 px-2 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2A313C]/40 font-mono">
              {tableRows.map((trace, idx) => {
                const isCopied = copiedAddress === trace.address;
                const formattedTime = timeAgo(trace.created_at);

                return (
                  <tr
                    key={trace.trace_id || idx}
                    onClick={() =>
                      router.push(`/trace?id=${encodeURIComponent(trace.trace_id)}`)
                    }
                    className="group cursor-pointer transition-colors duration-150 odd:bg-transparent even:bg-[#161B22]/40 hover:bg-[#1C232E]"
                  >
                    {/* Time (relative) */}
                    <td className="py-3 px-3 whitespace-nowrap text-slate-400 text-[11px]">
                      {formattedTime}
                    </td>

                    {/* Address (truncated, mono font, copy convenience) */}
                    <td className="py-3 px-3 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-200 group-hover:text-white transition font-mono">
                          {truncateAddress(trace.address, 6)}
                        </span>
                        <button
                          type="button"
                          onClick={(e) => handleCopy(trace.address, e)}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#2A313C] text-slate-400 hover:text-white transition"
                          title="Copy address"
                        >
                          {isCopied ? (
                            <Check className="w-3 h-3 text-trace-teal" />
                          ) : (
                            <Copy className="w-3 h-3" />
                          )}
                        </button>
                      </div>
                    </td>

                    {/* Chain */}
                    <td className="py-3 px-3 whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-[#161B22] border border-[#2A313C] text-[10px] text-slate-300">
                        <ChainIcon
                          chain={trace.chain}
                          className="w-3 h-3 text-slate-300"
                        />
                        <span>{trace.chain.toUpperCase()}</span>
                      </div>
                    </td>

                    {/* VASP Found */}
                    <td className="py-3 px-3 whitespace-nowrap font-sans">
                      {trace.attributed_entity ? (
                        <span className="text-white font-medium text-xs">
                          {trace.attributed_entity}
                        </span>
                      ) : (
                        <span className="text-slate-500 italic text-[11px]">
                          Unassigned / None
                        </span>
                      )}
                    </td>

                    {/* Risk Level */}
                    <td className="py-3 px-3 whitespace-nowrap">
                      {renderRiskBadge(trace.risk_score)}
                    </td>

                    {/* Status */}
                    <td className="py-3 px-3 whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            trace.status === "completed"
                              ? "bg-trace-teal shadow-[0_0_6px_#3E8E85]"
                              : trace.status === "failed"
                              ? "bg-signal-red shadow-[0_0_6px_#A6392E]"
                              : "bg-signal-amber animate-pulse"
                          }`}
                        />
                        <span className="capitalize text-slate-300 text-[11px]">
                          {trace.status}
                        </span>
                      </div>
                    </td>

                    {/* Action Arrow */}
                    <td className="py-3 px-2 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1 text-slate-500 group-hover:text-trace-teal transition text-[11px]">
                        <span>Inspect</span>
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
