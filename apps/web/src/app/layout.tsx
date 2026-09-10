import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "VajraTrace",
  description: "Real-time cryptocurrency fraud-exchange identification",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable}`}>
      <body className={`${GeistSans.className} bg-ink text-white antialiased min-h-screen`}>
        {children}
      </body>
    </html>
  );
}
