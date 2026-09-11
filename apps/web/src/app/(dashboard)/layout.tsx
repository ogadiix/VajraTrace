"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Radio } from "lucide-react";
import { QueryProvider } from "@/components/providers/query-provider";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const pathname = usePathname();

  const navItems = [
    { name: "Trace", href: "/trace" },
    { name: "Analytics", href: "/analytics" },
    { name: "Reports", href: "/reports" },
  ];

  return (
    <div className="h-screen w-screen flex flex-col bg-[#12161C] text-white overflow-hidden select-none">
      {/* Top Bar — h-14 (56px), logo left, nav center, status right */}
      <header className="h-14 bg-[#12161C] border-b border-[#2A313C] px-5 flex items-center justify-between shrink-0 z-30">
        {/* Logo Left */}
        <Link href="/trace" className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded bg-[#162523] border border-trace-teal/50 flex items-center justify-center text-trace-teal shadow-sm group-hover:border-trace-teal transition">
            <Shield className="w-4 h-4 text-trace-teal" />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="font-sans font-bold text-base tracking-tight text-white">
              Vajra<span className="text-trace-teal">Trace</span>
            </span>
            <span className="text-[10px] text-slate-400 font-mono">Console</span>
          </div>
        </Link>

        {/* Nav Center */}
        <nav className="flex items-center gap-6 h-full">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href === "/trace" && (pathname === "/" || pathname.startsWith("/trace")));

            return (
              <Link
                key={item.name}
                href={item.href}
                className={`relative h-full flex items-center text-xs font-medium transition ${
                  isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <span>{item.name}</span>
                {isActive && (
                  <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#3E8E85]" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Status Right */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#161B22] border border-[#2A313C] text-[11px] text-slate-300">
            <span className="w-2 h-2 rounded-full bg-trace-teal shadow-[0_0_6px_#3E8E85]" />
            <span className="font-mono text-[10px]">System Operational</span>
          </div>
        </div>
      </header>

      {/* Center Stage Body — takes 100% remaining screen real estate */}
      <QueryProvider>
        <div className="flex-1 h-[calc(100vh-3.5rem)] overflow-hidden relative">
          {children}
        </div>
      </QueryProvider>
    </div>
  );
}

