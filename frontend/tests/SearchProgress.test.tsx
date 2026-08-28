import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SearchProgress } from "../src/components/SearchProgress";
import { ResumeProfile } from "../src/components/ResumeProfile";
import type { CandidateProfile } from "../src/types/resume";
import { emptyProfile } from "../src/types/resume";

describe("SearchProgress", () => {
  it("shows per-company progress including failures", () => {
    render(
      <SearchProgress
        state="running"
        companies={[
          {
            company: "Google",
            status: "completed",
            jobs_examined: 31,
            jobs_found: 5,
          },
          { company: "Stripe", status: "running", message: "Browsing careers site..." },
          { company: "Anthropic", status: "failed", message: null },
        ]}
        error={null}
      />
    );

    expect(screen.getByText(/Searching\.\.\./)).toBeInTheDocument();
    expect(screen.getByTestId("company-detail-Google")).toHaveTextContent(
      "31 jobs examined"
    );
    expect(screen.getByTestId("company-detail-Google")).toHaveTextContent(
      "5 relevant jobs"
    );
    expect(screen.getByTestId("company-detail-Stripe")).toHaveTextContent(
      /Browsing careers site/
    );
    // Failures are never hidden.
    expect(screen.getByTestId("company-detail-Anthropic")).toHaveTextContent(
      /Career site could not be navigated/
    );
  });

  it("surfaces the search error message", () => {
    render(
      <SearchProgress state="failed" companies={[]} error="Could not connect to Ollama." />
    );
    expect(screen.getByText(/Could not connect to Ollama/)).toBeInTheDocument();
    expect(screen.getByText(/Search failed/)).toBeInTheDocument();
  });

  it("renders nothing when no search has happened", () => {
    const { container } = render(<SearchProgress state={null} companies={[]} error={null} />);
    expect(container.firstChild).toBeNull();
  });
});

const profile: CandidateProfile = {
  ...emptyProfile(),
  name: "Shubh Sharma",
  target_roles: ["Backend Engineer", "Software Engineer"],
  skills: { ...emptyProfile().skills, languages: ["Go", "Python"], cloud: ["AWS"] },
  years_experience: 6,
  preferred_locations: ["Bangalore", "Remote"],
};

describe("ResumeProfile", () => {
  it("shows the extracted profile fields", () => {
    render(
      <ResumeProfile
        profile={profile}
        extracting={false}
        error={null}
        onEdit={() => {}}
      />
    );
    expect(screen.getByText("Shubh Sharma")).toBeInTheDocument();
    expect(screen.getByTestId("target-roles")).toHaveTextContent("Backend Engineer");
    expect(screen.getByTestId("skills")).toHaveTextContent("Go · Python · AWS");
    expect(screen.getByTestId("experience")).toHaveTextContent("6 years");
    expect(screen.getByTestId("locations")).toHaveTextContent("Bangalore · Remote");
  });

  it("shows a spinner while extracting", () => {
    render(
      <ResumeProfile profile={null} extracting error={null} onEdit={() => {}} />
    );
    expect(screen.getByText(/Extracting your profile/)).toBeInTheDocument();
  });

  it("shows friendly extraction errors", () => {
    render(
      <ResumeProfile
        profile={null}
        extracting={false}
        error="The LLM returned invalid structured data."
        onEdit={() => {}}
      />
    );
    expect(screen.getByText(/invalid structured data/)).toBeInTheDocument();
  });

  it("renders nothing when there is no profile yet", () => {
    const { container } = render(
      <ResumeProfile profile={null} extracting={false} error={null} onEdit={() => {}} />
    );
    expect(container.firstChild).toBeNull();
  });
});
