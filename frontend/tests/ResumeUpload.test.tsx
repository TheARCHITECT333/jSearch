import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResumeUpload } from "../src/components/ResumeUpload";

const LATEX = "\\documentclass{article}\n\\begin{document}Hello\n\\end{document}";

describe("ResumeUpload", () => {
  beforeEach(() => window.localStorage.clear());

  it("shows empty state and loads a .tex file", async () => {
    const onLoaded = vi.fn();
    render(<ResumeUpload resumeLatex={null} onLoaded={onLoaded} />);

    expect(screen.queryByText("Resume loaded ✓")).not.toBeInTheDocument();

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File([LATEX], "resume.tex", { type: "text/plain" });
    await userEvent.upload(input!, file);

    expect(onLoaded).toHaveBeenCalledWith(LATEX);
  });

  it("supports pasting LaTeX source", async () => {
    const user = userEvent.setup();
    const onLoaded = vi.fn();
    render(<ResumeUpload resumeLatex={null} onLoaded={onLoaded} />);

    await user.click(screen.getByTestId("paste-button"));
    const area = screen.getByLabelText(/LaTeX source/);
    await user.type(area, LATEX);
    await user.click(screen.getByTestId("save-paste-button"));

    expect(onLoaded).toHaveBeenCalledWith(expect.stringContaining("documentclass"));
  });

  it("disables saving an empty paste", async () => {
    const user = userEvent.setup();
    render(<ResumeUpload resumeLatex={null} onLoaded={vi.fn()} />);
    await user.click(screen.getByTestId("paste-button"));
    expect(screen.getByTestId("save-paste-button")).toBeDisabled();
  });

  it("marks loaded state and can show the original LaTeX source", async () => {
    const user = userEvent.setup();
    render(<ResumeUpload resumeLatex={LATEX} onLoaded={vi.fn()} />);

    expect(screen.getByText("Resume loaded ✓")).toBeInTheDocument();

    await user.click(screen.getByText(/View resume source/));
    expect(screen.getByTestId("latex-source")).toHaveTextContent(/documentclass/);
  });
});
