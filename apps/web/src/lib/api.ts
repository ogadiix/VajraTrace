/**
 * API client — Typed fetch & WebSocket client for VajraTrace backend.
 * Error handling: never throws raw exceptions to the UI.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChainType = "BTC" | "ETH" | "TRON" | string;

export interface TraceRequest {
  address: string;
  chain: string;
  depth?: number;
  include_agent_narrative?: boolean;
  submitted_by?: string;
  notes?: string;
}

export interface TraceResponse {
  trace_id: string;
  status: string;
  submitted_at: string;
  ws_url: string;
}

export interface ProgressInfo {
  step: string;
  pct: number;
}

export interface TraceStatusResponse {
  trace_id: string;
  status: "processing" | "completed" | "failed" | string;
  progress?: ProgressInfo;
  result?: {
    source_address?: string;
    chain?: string;
    depth_reached?: number;
    node_count?: number;
    edge_count?: number;
    chains_involved?: string[];
    total_value_moved?: string;
    stale_data?: boolean;
    trace_duration_ms?: number;
    attribution?: {
      entity_name?: string;
      confidence?: number;
    };
    risk_score?: number;
    agent_narrative?: string;
  } | null;
  started_at: string;
  completed_at?: string;
  elapsed_seconds?: number;
}

export interface CytoscapeNodeData {
  id: string;
  label?: string;
  chain?: string;
  risk_score?: number;
  entity_label?: string | null;
  total_received?: string;
  total_sent?: string;
  tx_count?: number;
  first_seen?: string | null;
  last_seen?: string | null;
  is_source?: boolean;
  is_mixer?: boolean;
  is_exchange?: boolean;
  cluster_id?: string | null;
}

export interface CytoscapeNode {
  data: CytoscapeNodeData;
}

export interface CytoscapeEdgeData {
  id: string;
  source: string;
  target: string;
  value: string;
  token: string;
  timestamp?: string;
  chain?: string;
  tx_hash?: string;
  block_number?: number;
}

export interface CytoscapeEdge {
  data: CytoscapeEdgeData;
}

export interface GraphResponse {
  nodes: CytoscapeNode[];
  edges: CytoscapeEdge[];
}

export interface EvidenceEntry {
  id: string;
  step_number: number;
  action: string;
  description: string;
  result_summary?: string | null;
  confidence?: number | null;
  raw_data?: Record<string, unknown> | null;
  integrity_hash: string;
  created_at: string;
}

export interface EvidenceResponse {
  trace_id: string;
  evidence: EvidenceEntry[];
}

export interface RecentTrace {
  trace_id: string;
  address: string;
  chain: string;
  status: string;
  attributed_entity?: string | null;
  risk_score?: number | null;
  created_at: string;
}

export interface RecentTracesResponse {
  traces: RecentTrace[];
}

export interface TopExchange {
  name: string;
  count: number;
}

export interface AnalyticsOverview {
  total_traces: number;
  total_identified: number;
  avg_trace_time_ms: number;
  top_exchanges: TopExchange[];
  recent_traces: RecentTrace[];
}

export interface ReportGenerateResponse {
  report_id: string;
  download_url: string;
}

// ---------------------------------------------------------------------------
// Generic Fetch Wrapper
// ---------------------------------------------------------------------------

async function safeFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<{ data: T | null; error: string | null }> {
  try {
    const url = `${API_BASE}${endpoint}`;
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!res.ok) {
      if (res.status === 429) {
        return {
          data: null,
          error: "Etherscan rate limit reached — showing cached data from 4 min ago",
        };
      }
      if (res.status === 404) {
        return { data: null, error: "Requested resource was not found" };
      }
      if (res.status === 422) {
        const detail = await res.text().catch(() => "");
        return {
          data: null,
          error: detail.includes("Invalid address")
            ? "Unrecognized wallet address format"
            : "Validation error on submission",
        };
      }
      return {
        data: null,
        error: `Server responded with status ${res.status}`,
      };
    }

    const json = (await res.json()) as T;
    return { data: json, error: null };
  } catch (err: unknown) {
    const message =
      err instanceof Error
        ? err.message.includes("Failed to fetch")
          ? "Backend service currently unreachable"
          : err.message
        : "Network communication error";
    return { data: null, error: message };
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export async function submitTrace(
  req: TraceRequest
): Promise<{ data: TraceResponse | null; error: string | null }> {
  return safeFetch<TraceResponse>("/api/v1/trace/", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getTrace(
  traceId: string
): Promise<{ data: TraceStatusResponse | null; error: string | null }> {
  return safeFetch<TraceStatusResponse>(`/api/v1/trace/${traceId}`);
}

export async function getTraceGraph(
  traceId: string
): Promise<{ data: GraphResponse | null; error: string | null }> {
  return safeFetch<GraphResponse>(`/api/v1/trace/${traceId}/graph`);
}

export async function getTraceEvidence(
  traceId: string
): Promise<{ data: EvidenceResponse | null; error: string | null }> {
  return safeFetch<EvidenceResponse>(`/api/v1/trace/${traceId}/evidence`);
}

export async function getRecentTraces(): Promise<{
  data: RecentTracesResponse | null;
  error: string | null;
}> {
  return safeFetch<RecentTracesResponse>("/api/v1/analytics/recent");
}

export async function getAnalyticsOverview(): Promise<{
  data: AnalyticsOverview | null;
  error: string | null;
}> {
  return safeFetch<AnalyticsOverview>("/api/v1/analytics/overview");
}

export async function generateReportPdf(
  traceId: string
): Promise<{ data: ReportGenerateResponse | null; error: string | null }> {
  return safeFetch<ReportGenerateResponse>(`/api/v1/reports/${traceId}/pdf`, {
    method: "POST",
  });
}

export function getReportDownloadUrl(reportId: string): string {
  return `${API_BASE}/api/v1/reports/${reportId}/download`;
}

// ---------------------------------------------------------------------------
// WebSocket Live Trace Connection
// ---------------------------------------------------------------------------

export interface LiveTraceHandlers {
  onStep?: (step: string, pct: number) => void;
  onNode?: (node: Record<string, unknown>) => void;
  onEdge?: (edge: Record<string, unknown>) => void;
  onAttribution?: (attr: { vasp_name: string; confidence: number }) => void;
  onCompleted?: (result: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export function connectTraceLive(
  traceId: string,
  handlers: LiveTraceHandlers
): () => void {
  const wsUrl = API_BASE.replace(/^http/, "ws") + `/api/v1/trace/${traceId}/live`;
  let socket: WebSocket | null = null;
  let isClosedManually = false;

  try {
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      handlers.onOpen?.();
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { type, data } = payload;

        switch (type) {
          case "step":
            if (data?.step) {
              handlers.onStep?.(data.step, data.progress ?? 0);
            }
            break;
          case "node":
            handlers.onNode?.(data);
            break;
          case "edge":
            handlers.onEdge?.(data);
            break;
          case "attribution":
            if (data) {
              handlers.onAttribution?.(data);
            }
            break;
          case "completed":
            handlers.onCompleted?.(data);
            break;
          case "error":
            handlers.onError?.(data?.message || "Trace processing failed");
            break;
        }
      } catch {
        // silently ignore malformed frame
      }
    };

    socket.onerror = () => {
      if (!isClosedManually) {
        handlers.onError?.("WebSocket connection interrupted");
      }
    };

    socket.onclose = () => {
      handlers.onClose?.();
    };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "WebSocket failed to connect";
    handlers.onError?.(msg);
  }

  // Return unsubscribe/cleanup function
  return () => {
    isClosedManually = true;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
  };
}

