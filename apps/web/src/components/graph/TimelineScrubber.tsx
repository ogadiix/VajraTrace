"use client";

import React, { useMemo } from "react";
import { useTraceStore } from "@/stores/trace-store";
import { formatTimestamp } from "@/lib/utils";
import { Play, Pause, RotateCcw, Clock } from "lucide-react";

export function TimelineScrubber() {
  const {
    timelineMinTimestamp,
    timelineMaxTimestamp,
    timelineCurrentTimestamp,
    setTimelineFilter,
    graph,
  } = useTraceStore();

  const [isPlaying, setIsPlaying] = React.useState(false);

  const hasTimeline =
    timelineMinTimestamp !== null &&
    timelineMaxTimestamp !== null &&
    timelineMaxTimestamp > timelineMinTimestamp;

  const minTime = timelineMinTimestamp ?? 0;
  const maxTime = timelineMaxTimestamp ?? 100;
  const currentTime = timelineCurrentTimestamp ?? maxTime;

  // Percentage for progress fill (0-100)
  const currentPct = useMemo(() => {
    if (!hasTimeline || maxTime <= minTime) return 100;
    return Math.max(
      0,
      Math.min(100, Math.round(((currentTime - minTime) / (maxTime - minTime)) * 100))
    );
  }, [hasTimeline, minTime, maxTime, currentTime]);

  // Count active edges within current scrubber time
  const visibleEdgeCount = useMemo(() => {
    if (!graph?.edges) return 0;
    if (!timelineCurrentTimestamp) return graph.edges.length;
    return graph.edges.filter((e) => {
      if (!e.data.timestamp) return true;
      return new Date(e.data.timestamp).getTime() <= timelineCurrentTimestamp;
    }).length;
  }, [graph, timelineCurrentTimestamp]);

  // Handle Play/Replay animation
  React.useEffect(() => {
    if (!isPlaying || !hasTimeline) return;

    const interval = setInterval(() => {
      const step = (maxTime - minTime) / 40; // 40 steps
      const nextTime = (useTraceStore.getState().timelineCurrentTimestamp ?? minTime) + step;

      if (nextTime >= maxTime) {
        setTimelineFilter(maxTime);
        setIsPlaying(false);
      } else {
        setTimelineFilter(nextTime);
      }
    }, 150);

    return () => clearInterval(interval);
  }, [isPlaying, hasTimeline, minTime, maxTime, setTimelineFilter]);

  if (!hasTimeline) {
    return null;
  }

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    const targetTime = minTime + (val / 100) * (maxTime - minTime);
    setTimelineFilter(targetTime);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setTimelineFilter(maxTime);
  };

  const handleStartFromBeginning = () => {
    setIsPlaying(false);
    setTimelineFilter(minTime);
  };

  return (
    <div className="absolute bottom-4 left-6 right-6 z-20 pointer-events-auto">
      <div className="bg-[#12161C]/95 backdrop-blur-md border border-[#2A313C] rounded-lg px-4 py-2.5 shadow-xl flex items-center gap-4 text-xs">
        {/* Controls */}
        <div className="flex items-center gap-1.5 shrink-0 border-r border-[#2A313C] pr-3">
          <button
            type="button"
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-1.5 rounded hover:bg-[#2A313C]/60 text-slate-300 hover:text-white transition"
            title={isPlaying ? "Pause timeline replay" : "Play timeline replay"}
          >
            {isPlaying ? (
              <Pause className="w-3.5 h-3.5 text-trace-teal" />
            ) : (
              <Play className="w-3.5 h-3.5 text-trace-teal fill-current" />
            )}
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="p-1.5 rounded hover:bg-[#2A313C]/60 text-slate-400 hover:text-white transition"
            title="Reset to latest"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleStartFromBeginning}
            className="px-1.5 py-0.5 rounded text-[10px] text-slate-400 hover:text-white hover:bg-[#2A313C]/60"
            title="Jump to first transaction"
          >
            Start
          </button>
        </div>

        {/* Earliest timestamp */}
        <div className="shrink-0 flex items-center gap-1.5 text-slate-400 font-mono text-[11px]">
          <Clock className="w-3 h-3 text-slate-500" />
          <span>{formatTimestamp(new Date(minTime).toISOString())}</span>
        </div>

        {/* Track / Draggable Scrubber */}
        <div className="flex-1 relative flex items-center">
          <input
            type="range"
            min={0}
            max={100}
            value={currentPct}
            onChange={handleSliderChange}
            className="w-full h-1.5 bg-[#2A313C] rounded-lg appearance-none cursor-pointer accent-trace-teal focus:outline-none"
            style={{
              background: `linear-gradient(to right, #3E8E85 ${currentPct}%, #2A313C ${currentPct}%)`,
            }}
          />
        </div>

        {/* Latest timestamp */}
        <div className="shrink-0 text-slate-400 font-mono text-[11px]">
          <span>{formatTimestamp(new Date(maxTime).toISOString())}</span>
        </div>

        {/* Current Active Hop Status */}
        <div className="shrink-0 border-l border-[#2A313C] pl-3 flex items-center gap-2">
          <span className="text-[11px] text-slate-400">Showing:</span>
          <span className="px-2 py-0.5 bg-[#1a1f2e] border border-[#2A313C] rounded font-mono text-[11px] text-trace-teal">
            {visibleEdgeCount} / {graph?.edges?.length ?? 0} txs
          </span>
        </div>
      </div>
    </div>
  );
}
