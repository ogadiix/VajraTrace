"use client";

import React, { useEffect } from "react";
import { useTraceStore, detectChainFromAddress } from "@/stores/trace-store";
import { ChainIcon } from "./ChainIcon";
import { truncateAddress, timeAgo } from "@/lib/utils";
import { Slider } from "@/components/ui/slider";
import { History, Shield, ArrowRight } from "lucide-react";

export function LeftRail() {
  const {
    address,
    chain,
    depth,
    status,
    progressStep,
    recentTraces,
    setAddress,
    setDepth,
    startTrace,
    fetchRecentTraces,
  } = useTraceStore();

  const isTracing =
    status === "validating" ||
    status === "fetching" ||
    status === "clustering" ||
    status === "attributing" ||
    status === "scoring";

  useEffect(() => {
    fetchRecentTraces();
  }, [fetchRecentTraces]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setAddress(e.target.value);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!address.trim() || isTracing) return;
    startTrace();
  };

  const handleSelectRecent = (recentAddr: string) => {
    setAddress(recentAddr);
    startTrace(recentAddr, depth);
  };

  // Helper for risk badge styling in recent list
  const getRiskBadge = (score?: number | null) => {
    if (score === null || score === undefined) {
      return (
        <span className="px-1.5 py-0.2 rounded text-[10px] bg-[#2A313C] text-slate-400 font-mono">
          —
        </span>
      );
    }
    const val = score <= 1 && score > 0 ? Math.round(score * 100) : Math.round(score);
    if (val >= 70) {
      return (
        <span className="px-1.5 py-0.2 rounded text-[10px] bg-signal-red/20 text-signal-red border border-signal-red/40 font-mono font-medium">
          {val} High
        </span>
      );
    }
    if (val >= 40) {
      return (
        <span className="px-1.5 py-0.2 rounded text-[10px] bg-signal-amber/20 text-signal-amber border border-signal-amber/40 font-mono font-medium">
          {val} Med
        </span>
      );
    }
    return (
      <span className="px-1.5 py-0.2 rounded text-[10px] bg-trace-teal/20 text-trace-teal border border-trace-teal/40 font-mono font-medium">
        {val} Low
      </span>
    );
  };

  return (
    <aside className="w-[260px] h-full flex flex-col bg-[#12161C] border-r border-[#2A313C] select-none shrink-0 overflow-hidden">
      {/* Top Section: Wallet Input & Settings */}
      <div className="p-4 border-b border-[#2A313C] flex flex-col gap-4">
        <div>
          <label
            htmlFor="wallet-input"
            className="text-sm font-medium text-slate-400 block mb-2"
          >
            Trace target
          </label>

          {/* Large text input with chain detection icon */}
          <div className="relative flex items-center">
            <input
              id="wallet-input"
              type="text"
              value={address}
              onChange={handleInputChange}
              placeholder="Trace this wallet..."
              disabled={isTracing}
              className="w-full bg-[#161B22] border border-[#2A313C] focus:border-trace-teal rounded-lg pl-3 pr-9 py-2.5 text-xs text-white placeholder:text-slate-500 font-mono transition outline-none"
            />
            <div className="absolute right-2.5 flex items-center justify-center pointer-events-none text-slate-400">
              <ChainIcon chain={chain} className="w-4 h-4 text-trace-teal" />
            </div>
          </div>

          <div className="flex items-center justify-between mt-1.5 px-0.5 text-[11px] text-slate-500">
            <span>Detected chain:</span>
            <span className="font-mono text-slate-300 font-medium">{chain}</span>
          </div>
        </div>

        {/* Trace Depth Slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm font-medium text-slate-400">
            <span>Trace depth</span>
            <span className="font-mono text-xs text-trace-teal font-semibold">
              {depth} {depth === 1 ? "hop" : "hops"}
            </span>
          </div>
          <Slider
            min={1}
            max={5}
            step={1}
            value={[depth]}
            onValueChange={(vals) => {
              if (Array.isArray(vals)) {
                setDepth(vals[0]);
              } else if (typeof vals === "number") {
                setDepth(vals);
              }
            }}
            disabled={isTracing}
            className="w-full"
          />
          <div className="flex justify-between text-[10px] font-mono text-slate-600 px-0.5">
            <span>1</span>
            <span>2</span>
            <span>3</span>
            <span>4</span>
            <span>5</span>
          </div>
        </div>

        {/* TRACE Button with Real Progress Text */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isTracing || !address.trim()}
          className="w-full py-2.5 px-4 bg-trace-teal hover:bg-trace-teal/90 disabled:bg-[#1a2b29] disabled:text-slate-500 text-white rounded-lg font-semibold text-xs transition shadow-md flex items-center justify-center gap-2"
        >
          {isTracing ? (
            <span className="text-white font-medium text-xs truncate">
              {progressStep || "Validating address..."}
            </span>
          ) : (
            <>
              <span>TRACE</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </div>

      {/* Bottom Section: Recent Traces */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-[#2A313C] flex items-center justify-between">
          <span className="text-sm font-medium text-slate-400 flex items-center gap-1.5">
            <History className="w-3.5 h-3.5 text-slate-500" />
            Recent Traces
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            {recentTraces.length}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-[#2A313C]/40">
          {recentTraces.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500">
              No recent investigations yet
            </div>
          ) : (
            recentTraces.map((trace) => (
              <button
                key={trace.trace_id || trace.address}
                type="button"
                onClick={() => handleSelectRecent(trace.address)}
                className="w-full p-3 text-left hover:bg-[#161B22] transition flex flex-col gap-1.5 group"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-slate-300 group-hover:text-trace-teal transition truncate max-w-[140px]">
                    {truncateAddress(trace.address, 5)}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {timeAgo(trace.created_at)}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-[#1a1f2e] border border-[#2A313C] text-slate-300">
                    {trace.chain}
                  </span>
                  {getRiskBadge(trace.risk_score)}
                </div>

                {trace.attributed_entity && (
                  <span className="text-[11px] text-slate-400 truncate">
                    {trace.attributed_entity}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}
