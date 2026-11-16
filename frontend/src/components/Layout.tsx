import { useState, type ReactNode } from "react";

interface Props {
  /** The dark setup tile: everything you configure, not what you read. */
  rail: ReactNode;
  /** Right side of the frosted sub-nav (the view switcher). */
  subnav?: ReactNode;
  children: ReactNode;
}

/** global-nav (black, 44px) -> sub-nav-frosted (parchment, 52px) ->
 * dark setup tile beside a parchment readout. The colour change between
 * rail and readout is the divider; nothing else draws one. */
export function Layout({ rail, subnav, children }: Props) {
  // On a narrow screen the rail would push the readout a full screen down,
  // so it starts collapsed there. At lg it is always shown.
  const [railOpen, setRailOpen] = useState(false);

  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-30">
        <nav className="flex h-11 items-center justify-between bg-nav px-5 text-[12px] tracking-fine text-white">
          <span className="font-semibold">jsearch</span>
          <span className="flex items-center gap-2 text-ink-muted">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-primary-dark" />
            <span className="hidden sm:inline">Nothing leaves this machine</span>
            <span className="sm:hidden">Local</span>
          </span>
        </nav>
        <div className="frosted flex h-[52px] items-center justify-between gap-4 border-b border-black/[0.08] bg-paper/80 px-5">
          <span className="tagline truncate text-ink">Job search</span>
          {subnav}
        </div>
      </header>

      <div className="lg:flex lg:items-start">
        <aside
          aria-label="Setup"
          className="bg-ink-tile text-ink-text lg:sticky lg:top-[96px] lg:h-[calc(100vh-96px)]
                     lg:w-[360px] lg:shrink-0 lg:overflow-y-auto"
        >
          <button
            type="button"
            onClick={() => setRailOpen((open) => !open)}
            aria-expanded={railOpen}
            className="flex w-full items-center justify-between px-6 py-4 lg:hidden"
          >
            <span className="eyebrow text-ink-muted">Setup</span>
            <span className="text-[14px] text-primary-dark">{railOpen ? "Hide" : "Show"}</span>
          </button>
          <div className={railOpen ? "block" : "hidden lg:block"}>{rail}</div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-12 sm:px-8 lg:py-16">
          <div className="mx-auto max-w-[980px] space-y-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
