import { useState, type ReactNode } from "react";

interface Props {
  /** The dark control rail: everything you set up, not what you read. */
  rail: ReactNode;
  children: ReactNode;
}

/** Two-zone shell.
 *
 * Setup happens roughly weekly; triage happens every session. The old flat
 * stack gave both the same vertical space, so every visit meant scrolling
 * past the resume uploader to reach the jobs. Controls now live in a fixed
 * dark rail, and the light column belongs entirely to the readout.
 */
export function Layout({ rail, children }: Props) {
  // On a narrow screen the rail would push the results a full screen down,
  // so it starts collapsed there. At lg it is always the rail and this
  // state is ignored.
  const [railOpen, setRailOpen] = useState(false);

  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-30 border-b border-ink-line bg-ink">
        <div className="flex items-center justify-between px-5 py-3">
          <div className="flex items-baseline gap-3">
            <span className="text-[15px] font-bold tracking-tightest text-ink-text">
              jsearch
            </span>
            <span className="hidden text-[13px] text-ink-muted sm:inline">
              Job triage for one person
            </span>
          </div>
          <span className="token flex items-center gap-2 text-ink-faint">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-signal" />
            <span className="hidden sm:inline">Nothing leaves this machine</span>
            <span className="sm:hidden">Local</span>
          </span>
        </div>
      </header>

      <div className="lg:flex lg:items-start">
        {/* Rail: its own scroll on desktop so a long company list never
            pushes the readout out of reach. */}
        <aside
          aria-label="Setup"
          className="border-b border-ink-line bg-ink lg:sticky lg:top-[49px] lg:h-[calc(100vh-49px)]
                     lg:w-[340px] lg:shrink-0 lg:overflow-y-auto lg:border-b-0 lg:border-r"
        >
          <button
            type="button"
            onClick={() => setRailOpen((open) => !open)}
            aria-expanded={railOpen}
            className="flex w-full items-center justify-between px-5 py-3 lg:hidden"
          >
            <span className="eyebrow text-ink-faint">Setup</span>
            <span className="token text-ink-muted">
              {railOpen ? "Hide" : "Show"}
            </span>
          </button>
          <div className={railOpen ? "block" : "hidden lg:block"}>{rail}</div>
        </aside>

        <main className="min-w-0 flex-1 px-5 py-6 lg:px-8 lg:py-8">
          <div className="mx-auto max-w-3xl space-y-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
