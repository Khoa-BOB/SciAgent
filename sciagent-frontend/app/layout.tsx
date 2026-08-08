import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SciAgent",
  description: "Search and explore the SciAgent arXiv knowledge graph.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-neutral-50 text-neutral-900">
        <header className="border-b border-neutral-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-semibold tracking-tight">
                SciAgent
              </span>
              <span className="hidden text-sm text-neutral-500 sm:inline">
                knowledge graph explorer
              </span>
            </Link>
            <nav className="flex gap-5 text-sm font-medium text-neutral-600">
              <Link className="hover:text-neutral-900" href="/">
                Search
              </Link>
              <Link className="hover:text-neutral-900" href="/stats">
                Stats
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>
        <footer className="border-t border-neutral-200 py-6 text-center text-xs text-neutral-400">
          SciAgent &mdash; read-only view over the sciagent-backend KG service
        </footer>
      </body>
    </html>
  );
}
