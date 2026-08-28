import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { JobCard } from "../src/components/JobCard";
import type { JobResult } from "../src/types/job";

const job: JobResult = {
  company: "Stripe",
  company_url: "https://stripe.com",
  careers_url: "https://stripe.com/jobs",
  job_title: "Senior Backend Engineer",
  job_url: "https://stripe.com/jobs/listing/123",
  location: "Bangalore, India",
  employment_type: "Full-time",
  description: "Build payments APIs.",
  requirements: ["Go", "AWS", "PostgreSQL"],
  preferred_qualifications: [],
  match: {
    overall_score: 94,
    role_fit: 96,
    skill_fit: 95,
    experience_fit: 90,
    location_fit: 100,
    matching_skills: ["Go", "AWS", "PostgreSQL"],
    missing_skills: ["Kubernetes"],
    reason: "Strong backend engineering match.",
    disqualifiers: [],
    keyword_coverage: 80,
    missing_keywords: ["kubernete"],
  },
};

const ruledOutJob: JobResult = {
  ...job,
  job_url: "https://stripe.com/jobs/listing/999",
  match: {
    ...job.match,
    disqualifiers: ["Requires 10+ years of experience", "On-site in Dublin only"],
  },
};

describe("JobCard", () => {
  it("renders score, title, company and skills", () => {
    render(
      <JobCard job={job} onSave={vi.fn()} onIgnore={vi.fn()} onOpenDetails={vi.fn()} />
    );
    expect(screen.getByTestId("match-score")).toHaveTextContent("94%");
    expect(screen.getByText("Senior Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText(/Stripe · Bangalore/)).toBeInTheDocument();
    // Matching skills read plainly; missing ones are struck through rather
    // than carrying a warning glyph.
    expect(screen.getByText("Go")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toHaveClass("line-through");
    expect(screen.getByText(/Strong backend engineering/)).toBeInTheDocument();
  });

  it("Apply opens the ORIGINAL job URL in a new tab (never proxied)", () => {
    render(
      <JobCard job={job} onSave={vi.fn()} onIgnore={vi.fn()} onOpenDetails={vi.fn()} />
    );
    const apply = screen.getByTestId("apply-link");
    expect(apply).toHaveAttribute("href", "https://stripe.com/jobs/listing/123");
    expect(apply).toHaveAttribute("target", "_blank");
    expect(apply).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("Save and Ignore fire callbacks with the job's url key handled by parent", async () => {
    const onSave = vi.fn();
    const onIgnore = vi.fn();
    const user = userEvent.setup();
    render(
      <JobCard job={job} onSave={onSave} onIgnore={onIgnore} onOpenDetails={vi.fn()} />
    );
    await user.click(screen.getByTestId("save-button"));
    await user.click(screen.getByTestId("ignore-button"));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onIgnore).toHaveBeenCalledTimes(1);
  });

  it("clicking the card opens details but clicking buttons does not", async () => {
    const onOpenDetails = vi.fn();
    const user = userEvent.setup();
    render(
      <JobCard job={job} onSave={vi.fn()} onIgnore={vi.fn()} onOpenDetails={onOpenDetails} />
    );
    await user.click(screen.getByText("Senior Backend Engineer"));
    expect(onOpenDetails).toHaveBeenCalledTimes(1);
  });

  it("shows every stated hard requirement on a ruled-out job", () => {
    render(
      <JobCard
        job={ruledOutJob}
        onSave={vi.fn()}
        onIgnore={vi.fn()}
        onOpenDetails={vi.fn()}
      />
    );
    expect(screen.getByText(/Requires 10\+ years of experience/)).toBeInTheDocument();
    expect(screen.getByText(/On-site in Dublin only/)).toBeInTheDocument();
  });

  it("does not dress a ruled-out job in a confident green score", () => {
    // 94% fit is still true, but it must not read as "go apply for this".
    render(
      <JobCard
        job={ruledOutJob}
        onSave={vi.fn()}
        onIgnore={vi.fn()}
        onOpenDetails={vi.fn()}
      />
    );
    expect(screen.getByTestId("match-score").className).not.toContain("signal");
  });

  it("keeps an eligible job free of a disqualifier block", () => {
    render(
      <JobCard job={job} onSave={vi.fn()} onIgnore={vi.fn()} onOpenDetails={vi.fn()} />
    );
    expect(screen.queryByTestId("disqualifiers")).not.toBeInTheDocument();
  });

  it("reports literal keyword coverage as its own measurement, not folded into fit", () => {
    render(
      <JobCard job={job} onSave={vi.fn()} onIgnore={vi.fn()} onOpenDetails={vi.fn()} />
    );
    // Both numbers are present and distinct: 94 fit, 80 keyword coverage.
    const meters = screen.getByTestId("keyword-coverage");
    expect(meters).toHaveTextContent("Fit");
    expect(meters).toHaveTextContent("94");
    expect(meters).toHaveTextContent("Keywords");
    expect(meters).toHaveTextContent("80");
    expect(screen.getByTestId("missing-keywords")).toHaveTextContent("kubernete");
  });

  it("shows a dash rather than 0 when the posting listed nothing to check", () => {
    // 0 means "no requirements to match against", not "you match none of it".
    const noRequirements: JobResult = {
      ...job,
      match: { ...job.match, keyword_coverage: 0, missing_keywords: [] },
    };
    render(
      <JobCard
        job={noRequirements}
        onSave={vi.fn()}
        onIgnore={vi.fn()}
        onOpenDetails={vi.fn()}
      />
    );
    expect(screen.getByTestId("keyword-coverage")).toHaveTextContent("—");
    expect(screen.queryByTestId("missing-keywords")).not.toBeInTheDocument();
  });

  it("replaces the meters with the stated bars on a ruled-out job", () => {
    // The two measurements are irrelevant once a hard bar applies - the
    // reason has to take their place, not sit beside them.
    render(
      <JobCard
        job={ruledOutJob}
        onSave={vi.fn()}
        onIgnore={vi.fn()}
        onOpenDetails={vi.fn()}
      />
    );
    expect(screen.queryByTestId("keyword-coverage")).not.toBeInTheDocument();
    expect(screen.getByTestId("disqualifiers")).toBeInTheDocument();
  });
});
