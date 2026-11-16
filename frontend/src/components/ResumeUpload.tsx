import { useRef, useState } from "react";
import { pdfToText } from "../api/search";

interface Props {
  resumeLatex: string | null;
  onLoaded: (latex: string) => void;
}

export function ResumeUpload({ resumeLatex, onLoaded }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [viewSource, setViewSource] = useState(false);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);

  async function handleFile(file: File | undefined | null) {
    if (!file) return;
    setReadError(null);
    setReading(true);
    try {
      const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
      const text = isPdf ? await pdfToText(file) : await file.text();
      onLoaded(text);
      setViewSource(false);
    } catch (error) {
      setReadError(error instanceof Error ? error.message : "Could not read file.");
    } finally {
      setReading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <section aria-label="Resume" className="rail-section">
      <div className="flex items-center justify-between">
        <h2 className="rail-label">Resume</h2>
        {resumeLatex ? (
          <span className="token text-primary-dark">Resume loaded ✓</span>
        ) : (
          <span className="token text-ink-faint">Required</span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <input
          ref={fileInput}
          type="file"
          accept=".tex,.txt,.pdf,text/plain,application/pdf"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <button
          type="button"
          data-testid="upload-button"
          onClick={() => fileInput.current?.click()}
          disabled={reading}
          className="btn-rail-primary"
        >
          {reading ? "Reading PDF..." : "Upload .tex or .pdf"}
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

      {readError && (
        <p role="alert" className="mt-3 text-[14px] tracking-caption text-alert-dark">
          {readError}
        </p>
      )}

      {pasteOpen && (
        <div className="mt-3" data-testid="paste-area">
          <textarea
            aria-label="LaTeX source"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={8}
            placeholder={"\\documentclass{article}\n\\begin{document}...\n\\end{document}"}
            className="field !rounded-lg resize-y font-mono !text-[12px] leading-relaxed"
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
          className="rail-link mt-4"
        >
          {viewSource ? "Hide source" : "View resume source"}
        </button>
      )}

      {resumeLatex && viewSource && (
        <pre
          data-testid="latex-source"
          className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-deep p-4 font-mono text-[11px] leading-relaxed text-ink-muted"
        >
          {resumeLatex}
        </pre>
      )}
    </section>
  );
}
