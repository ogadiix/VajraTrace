import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: "VajraTrace — Cryptocurrency Fraud-Exchange Investigation Console",
  description:
    "Real-time automated blockchain forensics and cryptocurrency fraud-exchange identification platform.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`dark ${GeistSans.variable} ${GeistMono.variable} h-full`}
    >
      <body
        className={`${GeistSans.className} bg-[#12161C] text-[#F7F8FA] antialiased h-screen overflow-hidden p-0 m-0`}
      >
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
