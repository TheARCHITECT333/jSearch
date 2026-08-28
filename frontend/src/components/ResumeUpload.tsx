import { useRef, useState } from "react";

interface Props {
  resumeLatex: string | null;
  onLoaded: (latex: string) => void;
}

export function ResumeUpload({ resumeLatex, onLoaded }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [viewSource, setViewSource] = useState(false);

  async function handleFile(file: File | undefined | null) {
    if (!file) return;
    const text = await file.text();
    onLoaded(text);
    setViewSource(false);
  }

  return (
    <section aria-label="Resume" className="rail-section">
      <div className="flex items-center justify-between">
        <h2 className="rail-label">Resume</h2>
        {resumeLatex ? (
          <span className="token text-signal">Resume loaded ✓</span>
        ) : (
          <span className="token text-ink-faint">Required</span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <input
          ref={fileInput}
          type="file"
          accept=".tex,.txt,text/plain"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <button
          type="button"
          data-testid="upload-button"
          onClick={() => fileInput.current?.click()}
          className="btn-rail-primary"
        >
          Upload resume.tex
        </button>
        <button
          type="button"
          data-testid="paste-button"
          onClick={() => setPasteOpen((open) => !open)}
          className="btn-rail"
        >
          {pasteOpen ? "Close paste" : "Paste LaTeX"}
        </button>
      </div>

      {pasteOpen && (
        <div className="mt-3" data-testid="paste-area">
          <textarea
            aria-label="LaTeX source"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={8}
            placeholder={"\\documentclass{article}\n\\begin{document}...\n\\end{document}"}
            className="field resize-y text-[12px] leading-relaxed"
          />
          <button
            type="button"
            data-testid="save-paste-button"
            disabled={!pasteText.trim()}
            onClick={() => {
              onLoaded(pasteText);
              setPasteOpen(false);
              setPasteText("");
            }}
            className="btn-rail-primary mt-2"
          >
            Save resume
          </button>
        </div>
      )}

      {resumeLatex && (
        <button
          type="button"
          onClick={() => setViewSource((v) => !v)}
          className="mt-3 font-mono text-[11px] text-ink-faint underline underline-offset-2 transition-colors hover:text-ink-muted"
        >
          {viewSource ? "Hide source" : "View LaTeX source"}
        </button>
      )}

      {resumeLatex && viewSource && (
        <pre
          data-testid="latex-source"
          className="mt-2 max-h-56 overflow-auto rounded-control border border-ink-line bg-ink p-3 font-mono text-[11px] leading-relaxed text-ink-muted whitespace-pre-wrap"
        >
          {resumeLatex}
        </pre>
      )}
    </section>
  );
}
