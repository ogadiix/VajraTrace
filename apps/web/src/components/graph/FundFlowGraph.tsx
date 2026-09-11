"use client";

import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import cytoscape, { Core, NodeSingular, EdgeSingular } from "cytoscape";
import dagre from "cytoscape-dagre";
import { useTraceStore } from "@/stores/trace-store";
import { CytoscapeNode, CytoscapeEdge, CytoscapeNodeData } from "@/lib/api";
import { Maximize2, Download, Info } from "lucide-react";
import { TimelineScrubber } from "./TimelineScrubber";

// Register dagre layout plugin once
if (typeof window !== "undefined") {
  try {
    cytoscape.use(dagre);
  } catch {
    // Already registered
  }
}

interface ParticleData {
  id: string;
  pathD: string;
  color: string;
  duration: number;
  delay: number;
}

export function FundFlowGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  const {
    graph,
    selectNode,
    selectedNodeId,
    timelineCurrentTimestamp,
    address: currentTraceAddress,
  } = useTraceStore();

  const [particles, setParticles] = useState<ParticleData[]>([]);
  const [exchangeGlow, setExchangeGlow] = useState(false);
  const [hoveredEdgeInfo, setHoveredEdgeInfo] = useState<{
    value: string;
    token: string;
    x: number;
    y: number;
  } | null>(null);

  // Helper to calculate edge stroke width from transaction value
  const getEdgeWidth = useCallback((valStr: string) => {
    const val = parseFloat(valStr) || 0;
    if (val <= 0) return 1.5;
    if (val < 1) return 2;
    if (val < 10) return 3.5;
    if (val < 50) return 5;
    return 6;
  }, []);

  // Map risk to color: trace-teal (low) -> signal-amber (medium) -> signal-red (high)
  const getRiskColor = useCallback((score?: number) => {
    if (typeof score !== "number") return "#3E8E85";
    const s = score <= 1 && score > 0 ? score * 100 : score;
    if (s >= 70) return "#A6392E"; // signal-red
    if (s >= 40) return "#C8801F"; // signal-amber
    return "#3E8E85"; // trace-teal
  }, []);

  // Build Cytoscape elements and styles
  const initCytoscape = useCallback(() => {
    if (!containerRef.current || !graph) return;

    // Enforce top 200 nodes performance limit
    const nodes = graph.nodes.slice(0, 200);
    const validNodeIds = new Set(nodes.map((n) => n.data.id));
    const edges = graph.edges.filter(
      (e) => validNodeIds.has(e.data.source) && validNodeIds.has(e.data.target)
    );

    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const cy = cytoscape({
      container: containerRef.current,
      boxSelectionEnabled: false,
      autounselectify: false,
      style: ([
        // Default node style
        {
          selector: "node",
          style: {
            shape: "ellipse",
            width: 44,
            height: 44,
            "background-color": "#1a1f2e",
            "border-width": 2,
            "border-color": "#2A313C",
            label: "data(label)",
            color: "#F7F8FA",
            "font-size": "11px",
            "font-family": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            "text-valign": "bottom",
            "text-margin-y": "8px",
            "text-background-opacity": 0.8,
            "text-background-color": "#12161C",
            "text-background-padding": "3px",
            "text-background-shape": "roundrectangle",
            "transition-property": "border-color, border-width, background-color, transform",
            "transition-duration": "150ms",
          },
        },
        // Source node: 60px, border 2px #3E8E85, pulsing glow
        {
          selector: "node[?is_source]",
          style: {
            width: 60,
            height: 60,
            "border-color": "#3E8E85",
            "border-width": 2.5,
            "background-color": "#122524",
            "font-weight": "bold",
          },
        },
        // Identified exchange: 70px, border 2px gold #D4AF37, exchange name
        {
          selector: "node[?is_exchange]",
          style: {
            width: 70,
            height: 70,
            shape: "round-rectangle",
            "border-color": "#D4AF37",
            "border-width": 2.5,
            "background-color": "#262215",
            "font-weight": "bold",
          },
        },
        // Mixer / Suspicious node: octagon shape, border 2px #A6392E
        {
          selector: "node[?is_mixer]",
          style: {
            width: 54,
            height: 54,
            shape: "octagon",
            "border-color": "#A6392E",
            "border-width": 2.5,
            "background-color": "#281717",
          },
        },
        // Selected node highlight
        {
          selector: "node:selected",
          style: {
            "border-color": "#FFFFFF",
            "border-width": 3.5,
            "shadow-blur": 15,
            "shadow-color": "#3E8E85",
            "shadow-opacity": 0.8,
          },
        },
        // Default edge style: line, color #2A313C, curve-style bezier
        {
          selector: "edge",
          style: {
            width: "data(width)",
            "line-color": "#2A313C",
            "target-arrow-color": "#2A313C",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.9,
            opacity: 0.85,
            "line-dash-pattern": [6, 3],
            "transition-property": "line-color, target-arrow-color, width, opacity",
            "transition-duration": 150,
          },
        },
        // Active / Highlighted edge
        {
          selector: "edge.highlighted",
          style: {
            "line-color": "#3E8E85",
            "target-arrow-color": "#3E8E85",
            opacity: 1,
            width: 4,
          },
        },
        // Dimmed edge for timeline or selection
        {
          selector: "edge.dimmed",
          style: {
            opacity: 0.15,
            "line-color": "#1f242d",
            "target-arrow-color": "#1f242d",
          },
        },
      ] as any),
      elements: [
        ...nodes.map((n) => ({
          group: "nodes" as const,
          data: {
            ...n.data,
            label: n.data.entity_label || n.data.label || n.data.id.slice(0, 8) + "…",
          },
        })),
        ...edges.map((e) => ({
          group: "edges" as const,
          data: {
            ...e.data,
            width: getEdgeWidth(e.data.value),
          },
        })),
      ],
      layout: {
        name: "dagre",
        // @ts-expect-error dagre types
        rankDir: "LR",
        nodeSep: 60,
        rankSep: 110,
        animate: false,
      },
    });

    cyRef.current = cy;

    // THE ONE ORCHESTRATED MOMENT:
    // Staggered scale-in of nodes (0 -> 1, 200ms, staggered 50ms each)
    const allNodes = cy.nodes();
    allNodes.forEach((node, i) => {
      const origWidth = node.style("width");
      const origHeight = node.style("height");
      node.style({ width: 0, height: 0, opacity: 0 });

      setTimeout(() => {
        node.animate(
          {
            style: {
              width: origWidth,
              height: origHeight,
              opacity: 1,
            },
          },
          { duration: 200 }
        );
      }, i * 50);
    });

    // Edges draw in after node animation begins
    setTimeout(() => {
      cy.edges().animate(
        {
          style: { opacity: 0.85 },
        },
        { duration: 300 }
      );
    }, allNodes.length * 30);

    // Click node -> open right evidence drawer
    cy.on("tap", "node", (evt) => {
      const node = evt.target as NodeSingular;
      const data = node.data() as CytoscapeNodeData;
      selectNode(node.id(), data);
    });

    // Click canvas background -> deselect
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        selectNode(null, null);
      }
    });

    // Hover node -> highlight connected edges
    cy.on("mouseover", "node", (evt) => {
      const node = evt.target as NodeSingular;
      node.connectedEdges().addClass("highlighted");
      cy.edges().not(node.connectedEdges()).addClass("dimmed");
    });

    cy.on("mouseout", "node", () => {
      cy.edges().removeClass("highlighted dimmed");
    });

    // Hover edge -> tooltip with value + token
    cy.on("mouseover", "edge", (evt) => {
      const edge = evt.target as EdgeSingular;
      const renderedMid = edge.renderedMidpoint();
      setHoveredEdgeInfo({
        value: edge.data("value") || "0",
        token: edge.data("token") || "ETH",
        x: renderedMid.x,
        y: renderedMid.y,
      });
    });

    cy.on("mouseout", "edge", () => {
      setHoveredEdgeInfo(null);
    });

    // Compute particle paths after layout stabilizes
    const updateParticleTrajectories = () => {
      const cyInstance = cyRef.current;
      if (!cyInstance) return;
      const newParticles: ParticleData[] = [];

      cy.edges().forEach((edge, idx) => {
        const sourceNode = edge.source();
        const targetNode = edge.target();
        if (!sourceNode || !targetNode) return;

        const sp = sourceNode.renderedPosition();
        const tp = targetNode.renderedPosition();

        // Bezier midpoint approximation
        const mx = (sp.x + tp.x) / 2;
        const my = (sp.y + tp.y) / 2;
        const pathD = `M ${sp.x} ${sp.y} Q ${mx} ${my} ${tp.x} ${tp.y}`;

        // Color based on source risk
        const risk = sourceNode.data("risk_score") || 0.4;
        const color = getRiskColor(risk);

        // Recency mapping to duration (1.2s - 2.8s)
        const duration = 1.6 + (idx % 3) * 0.4;

        // Max 2-3 particles per edge
        newParticles.push({
          id: `p-${edge.id()}-1`,
          pathD,
          color,
          duration,
          delay: (idx * 0.15) % 1.5,
        });

        if (edge.data("value") && parseFloat(edge.data("value")) > 5) {
          newParticles.push({
            id: `p-${edge.id()}-2`,
            pathD,
            color,
            duration: duration * 1.1,
            delay: ((idx * 0.15) % 1.5) + 0.6,
          });
        }
      });

      setParticles(newParticles);
    };

    cy.one("layoutstop", () => {
      cy.fit(undefined, 50);
      updateParticleTrajectories();

      // Trigger deliberate exchange golden glow after particles arrive (~1.5s)
      setTimeout(() => {
        setExchangeGlow(true);
        const exchangeNodes = cy.nodes("[?is_exchange]");
        exchangeNodes.forEach((node) => {
          node.animate(
            {
              style: {
                "border-color": "#FFD700",
                "shadow-color": "#FFD700",
                "shadow-blur": 25,
                "shadow-opacity": 0.9,
              },
            },
            {
              duration: 1000,
              complete: () => {
                node.animate(
                  {
                    style: {
                      "border-color": "#D4AF37",
                      "shadow-color": "transparent",
                      "shadow-blur": 0,
                    },
                  },
                  { duration: 500 }
                );
              },
            }
          );
        });
      }, 1400);
    });

    // Recompute particle coordinates when user pans or zooms
    cy.on("pan zoom", () => {
      updateParticleTrajectories();
    });

    // Initial trigger in case layoutstop fired immediately
    setTimeout(updateParticleTrajectories, 300);
  }, [graph, getEdgeWidth, getRiskColor, selectNode]);

  // Initialize or re-render Cytoscape whenever the graph changes
  useEffect(() => {
    initCytoscape();
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [initCytoscape]);

  // Synchronize timeline scrubber with Cytoscape edges
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.edges().forEach((edge) => {
      const ts = edge.data("timestamp");
      if (!ts || !timelineCurrentTimestamp) {
        edge.removeClass("dimmed highlighted");
        return;
      }
      const edgeTime = new Date(ts).getTime();
      if (edgeTime <= timelineCurrentTimestamp) {
        edge.removeClass("dimmed").addClass("highlighted");
      } else {
        edge.removeClass("highlighted").addClass("dimmed");
      }
    });
  }, [timelineCurrentTimestamp]);

  // Fit View
  const handleFitView = () => {
    if (cyRef.current) {
      cyRef.current.fit(undefined, 50);
    }
  };

  // Export PNG
  const handleExportPNG = () => {
    if (!cyRef.current) return;
    const png64 = cyRef.current.png({
      full: true,
      scale: 2,
      bg: "#12161C",
    });
    const link = document.createElement("a");
    link.download = `vajratrace-${currentTraceAddress.slice(0, 10) || "graph"}.png`;
    link.href = png64;
    link.click();
  };

  return (
    <div className="relative w-full h-full bg-[#0e1217] overflow-hidden select-none">
      {/* Cytoscape Canvas Container */}
      <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Hardware-accelerated SVG Particle Flow Overlay */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none z-10">
        <defs>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        {particles.map((p) => (
          <g key={p.id}>
            <circle r="3.5" fill={p.color} filter="url(#glow)">
              <animateMotion
                path={p.pathD}
                dur={`${p.duration}s`}
                begin={`${p.delay}s`}
                repeatCount="indefinite"
                keyPoints="0;1"
                keyTimes="0;1"
              />
            </circle>
          </g>
        ))}
      </svg>

      {/* Hover Edge Tooltip */}
      {hoveredEdgeInfo && (
        <div
          className="absolute z-30 pointer-events-none bg-[#12161C] border border-[#2A313C] rounded px-2.5 py-1 text-xs shadow-lg transform -translate-x-1/2 -translate-y-full"
          style={{ left: hoveredEdgeInfo.x, top: hoveredEdgeInfo.y - 12 }}
        >
          <span className="font-mono text-trace-teal font-semibold">
            {hoveredEdgeInfo.value}
          </span>{" "}
          <span className="text-slate-400 text-[11px]">{hoveredEdgeInfo.token}</span>
        </div>
      )}

      {/* Top-right Graph Actions: Fit View & Export PNG */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
        <button
          type="button"
          onClick={handleFitView}
          className="px-2.5 py-1.5 bg-[#12161C]/90 hover:bg-[#1f2631] border border-[#2A313C] rounded-md text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 shadow-sm transition"
          title="Fit graph to view"
        >
          <Maximize2 className="w-3.5 h-3.5" />
          <span>Fit view</span>
        </button>
        <button
          type="button"
          onClick={handleExportPNG}
          className="px-2.5 py-1.5 bg-[#12161C]/90 hover:bg-[#1f2631] border border-[#2A313C] rounded-md text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 shadow-sm transition"
          title="Export graph as PNG image"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export PNG</span>
        </button>
      </div>

      {/* Bottom Timeline Scrubber */}
      <TimelineScrubber />
    </div>
  );
}
