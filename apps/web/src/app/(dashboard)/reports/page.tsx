"use client";

import React, { useState } from "react";
import { FileText, Download, ShieldCheck, Check, Calendar, Hash } from "lucide-react";
import { truncateAddress } from "@/lib/utils";

interface MockReport {
  id: string;
  caseId: string;
  title: string;
  targetAddress: string;
  chain: string;
  attributedEntity: string;
  riskScore: number;
  date: string;
  status: "Finalized" | "Ready";
}

const SAMPLE_REPORTS: MockReport[] = [
  {
    id: "rep-9821",
    caseId: "CASE-2026-0819",
    title: "Forensic Attribution & Flow Dossier",
    targetAddress: "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
    chain: "ETH",
    attributedEntity: "Binance 14 (Hot Wallet)",
    riskScore: 78,
    date: "2026-09-11 14:22 UTC",
    status: "Finalized",
  },
  {
    id: "rep-9820",
    caseId: "CASE-2026-0814",
    title: "Sanctioned Mixer Proximity Analysis",
    targetAddress: "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    chain: "BTC",
    attributedEntity: "Blender.io Deposit Node",
    riskScore: 92,
    date: "2026-09-10 18:40 UTC",
    status: "Finalized",
  },
  {
    id: "rep-9819",
    caseId: "CASE-2026-0811",
    title: "Exchange Sweep Attribution Report",
    targetAddress: "TX9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y",
    chain: "TRON",
    attributedEntity: "OKX Settlement Sub-account",
    riskScore: 34,
    date: "2026-09-09 11:15 UTC",
    status: "Finalized",
  },
];

export default function ReportsPage() {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const handleDownload = (report: MockReport) => {
    setDownloadingId(report.id);
    const data = {
      report_title: report.title,
      case_reference: report.caseId,
      target_wallet: report.targetAddress,
      network: report.chain,
      attributed_entity: report.attributedEntity,
      risk_score: report.riskScore,
      audit_integrity: "SHA256: 9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f",
      generated_timestamp: report.date,
      classification: "LAW ENFORCEMENT & COMPLIANCE CONFIDENTIAL",
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `vajratrace_${report.caseId}.json`;
    a.click();

    setTimeout(() => setDownloadingId(null), 1200);
  };

  return (
    <div className="h-full w-full overflow-y-auto p-6 space-y-6 select-none bg-[#0e1217]">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-white">
          Investigation Reports
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Cryptographically verified evidentiary dossiers and court-ready exports
        </p>
      </div>

      {/* Reports Table / List */}
      <div className="bg-[#12161C] border border-[#2A313C] rounded-lg overflow-hidden shadow-xl">
        <div className="px-5 py-3.5 border-b border-[#2A313C] flex items-center justify-between text-xs text-slate-400">
          <span className="font-medium">Recent Investigation Dossiers</span>
          <span className="font-mono text-slate-500">
            {SAMPLE_REPORTS.length} reports
          </span>
        </div>

        <div className="divide-y divide-[#2A313C]">
          {SAMPLE_REPORTS.map((report) => (
            <div
              key={report.id}
              className="p-4 hover:bg-[#161B22] transition flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-[#1a1f2e] text-trace-teal border border-[#2A313C] font-semibold">
                    {report.caseId}
                  </span>
                  <span className="text-xs font-semibold text-white">
                    {report.title}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                  <span className="font-mono flex items-center gap-1">
                    <Hash className="w-3 h-3 text-slate-500" />
                    {truncateAddress(report.targetAddress, 6)}
                  </span>
                  <span className="px-1.5 py-0.2 rounded bg-[#1a1f2e] text-[10px] font-mono border border-[#2A313C] text-slate-300">
                    {report.chain}
                  </span>
                  <span className="text-slate-300">
                    Attributed: <strong className="text-white">{report.attributedEntity}</strong>
                  </span>
                  <span className="flex items-center gap-1 text-[11px] text-slate-500">
                    <Calendar className="w-3 h-3" />
                    {report.date}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => handleDownload(report)}
                  className="py-1.5 px-3 bg-trace-teal hover:bg-trace-teal/90 text-white rounded text-xs font-medium flex items-center gap-1.5 transition shadow-sm"
                >
                  {downloadingId === report.id ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-white" />
                      <span>Downloaded</span>
                    </>
                  ) : (
                    <>
                      <Download className="w-3.5 h-3.5" />
                      <span>Download dossier</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

