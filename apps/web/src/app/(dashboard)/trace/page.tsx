"use client";

import React, { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useTraceStore } from "@/stores/trace-store";
import { LeftRail } from "@/components/trace/LeftRail";
import { RightDrawer } from "@/components/trace/RightDrawer";
import { FundFlowGraph } from "@/components/graph/FundFlowGraph";
import { Check, ShieldAlert } from "lucide-react";

const PIPELINE_STEPS = [
  "Validating address...",
  "Fetching transactions (47 found)...",
  "Clustering addresses...",
  "Identifying exchanges...",
  "Scoring risk...",
];

function TracePageContent() {
  const searchParams = useSearchParams();
  const idParam = searchParams.get("id");

  const {
    status,
    progressStep,
    completedSteps,
    graph,
    errorMessage,
    recentTraces,
    startTrace,
    setAddress,
    traceId,
  } = useTraceStore();

  useEffect(() => {
    if (idParam && idParam !== traceId && status === "idle") {
      const match = recentTraces.find((t) => t.trace_id === idParam);
      if (match) {
        setAddress(match.address);
        startTrace(match.address);
      } else if (idParam.startsWith("0x") || idParam.startsWith("1") || idParam.startsWith("3") || idParam.startsWith("bc1") || idParam.startsWith("T")) {
        setAddress(idParam);
        startTrace(idParam);
      } else {
        // Fallback trace for sample trace id
        const defaultSampleAddr = "0x71C8401367793a7317769e3B05E15f5aD3B3189A";
        setAddress(defaultSampleAddr);
        startTrace(defaultSampleAddr);
      }
    }
  }, [idParam, traceId, status, recentTraces, setAddress, startTrace]);

  const isTracing =
    status === "validating" ||
    status === "fetching" ||
    status === "clustering" ||
    status === "attributing" ||
    status === "scoring";

  const isResolved = status === "completed" && graph && graph.nodes.length > 0;

  return (
    <div className="w-full h-full flex flex-row bg-[#12161C] overflow-hidden select-none">
      {/* LEFT RAIL — w-[260px], border-r border-[#2A313C] */}
      <LeftRail />

      {/* CENTER STAGE — takes maximum screen real estate */}
      <main className="flex-1 h-full relative overflow-hidden bg-[#0e1217] flex flex-col items-center justify-center">
        {/* Error message banner if any */}
        {errorMessage && (
          <div className="absolute top-4 left-6 right-6 z-40 bg-[#281717] border border-signal-red/60 text-signal-red px-4 py-2.5 rounded-lg text-xs flex items-center justify-between shadow-lg">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-signal-red shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <span className="text-[10px] font-mono text-slate-400">
              Cached / Local fallback available
            </span>
          </div>
        )}

        {/* State 1: EMPTY */}
        {!isTracing && !isResolved && (
          <div className="text-center px-4 max-w-md">
            <div className="w-12 h-12 rounded-full bg-[#161B22] border border-[#2A313C] flex items-center justify-center mx-auto mb-3 text-slate-500">
              <span className="text-xl">⌘</span>
            </div>
            <p className="text-slate-400 text-sm font-medium">
              Paste a wallet address to begin tracing
            </p>
            <p className="text-slate-600 text-xs mt-1">
              Supports Bitcoin, Ethereum, and TRON blockchain addresses
            </p>
          </div>
        )}

        {/* State 2: TRACING — Real progress steps with checkmarks, NO spinners */}
        {isTracing && (
          <div className="w-full max-w-sm px-6 py-6 bg-[#12161C] border border-[#2A313C] rounded-xl shadow-2xl">
            <div className="text-xs font-medium text-slate-400 mb-4 pb-2 border-b border-[#2A313C] flex items-center justify-between">
              <span>Pipeline execution</span>
              <span className="font-mono text-trace-teal text-[11px]">
                In Progress
              </span>
            </div>

            <div className="space-y-3">
              {PIPELINE_STEPS.map((step) => {
                const isCompleted =
                  completedSteps.includes(step) && progressStep !== step;
                const isCurrent = progressStep === step;

                return (
                  <div
                    key={step}
                    className="flex items-center gap-3 text-xs transition"
                  >
                    <div
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] shrink-0 ${
                        isCompleted
                          ? "bg-trace-teal text-white"
                          : isCurrent
                          ? "border-2 border-trace-teal text-trace-teal"
                          : "border border-[#2A313C] text-transparent"
                      }`}
                    >
                      {isCompleted ? (
                        <Check className="w-2.5 h-2.5 stroke-[3]" />
                      ) : isCurrent ? (
                        <span className="w-1.5 h-1.5 rounded-full bg-trace-teal" />
                      ) : null}
                    </div>

                    <span
                      className={`font-mono text-xs ${
                        isCompleted
                          ? "text-slate-300"
                          : isCurrent
                          ? "text-white font-medium"
                          : "text-slate-600"
                      }`}
                    >
                      {step}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* State 3: RESOLVED — Full Cytoscape Graph filling 100% of Center Stage */}
        {isResolved && <FundFlowGraph />}
      </main>

      {/* RIGHT DRAWER — Slides in when node is clicked */}
      <RightDrawer />
    </div>
  );
}

export default function TracePage() {
  return (
    <Suspense
      fallback={
        <div className="w-full h-full bg-[#12161C] flex items-center justify-center text-xs font-mono text-slate-500">
          Loading trace workspace...
        </div>
      }
    >
      <TracePageContent />
    </Suspense>
  );
}

