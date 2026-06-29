import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

/**
 * Read-path Markdown renderer (0.8.1) — for the project "Background / Context" prose.
 *
 * Deliberately light: only `react-markdown` + `remark-gfm`, *not* the TipTap editor (which is
 * lazy-loaded for owners/admins). Public viewers render the stored Markdown without paying for the
 * editor bundle. Safe by default — `react-markdown` does **not** render raw HTML (no `rehype-raw`),
 * so embedded `<script>`/HTML in stored Markdown is shown as inert text, not executed.
 *
 * No `@tailwindcss/typography` in this project, so element styles are mapped to the console tokens
 * by hand via `components` overrides.
 */

// Console-token element styles (the project has no `prose` plugin).
const COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="mt-4 text-lg font-medium text-text first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-4 text-base font-medium text-text first:mt-0">{children}</h2>,
  h3: ({ children }) => (
    <h3 className="mt-3 text-[14px] font-medium text-text first:mt-0">{children}</h3>
  ),
  p: ({ children }) => <p className="text-[14px] leading-[1.6] text-text-soft">{children}</p>,
  ul: ({ children }) => (
    <ul className="ml-4 list-disc text-[14px] leading-[1.6] text-text-soft marker:text-text-faint">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="ml-4 list-decimal text-[14px] leading-[1.6] text-text-soft marker:text-text-faint">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="my-0.5">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-signal underline decoration-from-font underline-offset-2 hover:text-signal-strong"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-[color:var(--hairline-strong)] pl-3 text-text-mute">
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded-inset bg-panel-2 px-1 py-0.5 font-mono text-[12px] text-text">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-built bg-panel-2 p-3 font-mono text-[12px] text-text-soft">
      {children}
    </pre>
  ),
  hr: () => <hr className="border-[color:var(--hairline)]" />,
  strong: ({ children }) => <strong className="font-medium text-text">{children}</strong>,
};

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("grid gap-2", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
