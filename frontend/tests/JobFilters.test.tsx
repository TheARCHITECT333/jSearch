import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { JobFilters, applyFilters, type FilterState } from "../src/components/JobFilters";
import type { JobResult } from "../src/types/job";

const filters: FilterState = {
  company: "all",
  minScore: 0,
  savedOnly: false,
  showIgnored: false,
  location: "",
  sortBy: "score",
};

function job(
  overrides: Partial<JobResult> & { url: string; score: number }
): JobResult {
  const scores = {
    overall_score: overrides.score,
    role_fit: overrides.score,
    skill_fit: overrides.score,
    experience_fit: overrides.score,
    location_fit: overrides.score,
    matching_skills: [],
    missing_skills: [],
    reason: "",
    disqualifiers: [],
    keyword_coverage: 0,
    missing_keywords: [],
  };
  const { url, score, ...rest } = overrides;
  return {
    company: "Acme",
    company_url: null,
    careers_url: null,
    job_title: "Engineer",
    job_url: url,
    location: null,
    employment_type: null,
    description: "",
    requirements: [],
    preferred_qualifications: [],
    match: { ...scores, ...(overrides.match ?? {}) },
    ...rest,
  };
}

describe("applyFilters", () => {
  const jobs = [
    { ...job({ url: "u1", score: 95 }), company: "Stripe", job_title: "Backend", location: "Bangalore" },
    { ...job({ url: "u2", score: 65 }), company: "Google", job_title: "Analyst", location: "Remote" },
    { ...job({ url: "u3", score: 80 }), company: "Stripe", job_title: "Frontend", location: "Mumbai" },
  ];

  it("sorts by score descending by default", () => {
    const got = applyFilters(jobs, filters, {});
    expect(got.map((j) => j.job_url)).toEqual(["u1", "u3", "u2"]);
  });

  it("filters by minimum score", () => {
    const got = applyFilters(jobs, { ...filters, minScore: 70 }, {});
    expect(got.map((j) => j.job_url)).toEqual(["u1", "u3"]);
  });

  it("filters by company and sorts by title/company", () => {
    const byCompany = applyFilters(jobs, { ...filters, company: "Google" }, {});
    expect(byCompany.map((j) => j.job_url)).toEqual(["u2"]);

    const sorted = applyFilters(jobs, { ...filters, sortBy: "title" }, {});
    expect(sorted.map((j) => j.job_title)).toEqual(["Analyst", "Backend", "Frontend"]);
  });

  it("hides ignored jobs unless shown, supports saved-only", () => {
    const states = { u1: "ignored", u2: "saved" };

    expect(applyFilters(jobs, filters, states).map((j) => j.job_url)).toEqual([
      "u3",
      "u2",
    ]);
    expect(
      applyFilters(jobs, { ...filters, showIgnored: true }, states).map((j) => j.job_url)
    ).toEqual(["u1", "u3", "u2"]);
    expect(
      applyFilters(jobs, { ...filters, savedOnly: true }, states).map((j) => j.job_url)
    ).toEqual(["u2"]);
  });

  it("filters by location text", () => {
    const got = applyFilters(
      jobs,
      { ...filters, location: "bangalore" },
      {}
    );
    expect(got.map((j) => j.job_url)).toEqual(["u1"]);
  });
});

describe("JobFilters component", () => {
  it("emits changes for each control", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<JobFilters filters={filters} companies={["Stripe"]} onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText(/Filter by company/), "Stripe");
    expect(onChange).toHaveBeenLastCalledWith({ company: "Stripe" });

    await user.selectOptions(screen.getByLabelText(/Minimum match score/), "70");
    expect(onChange).toHaveBeenLastCalledWith({ minScore: 70 });

    await user.type(screen.getByLabelText(/Filter by location/), "Goa");
    expect(onChange).toHaveBeenLastCalledWith({ location: "a" });

    await user.click(screen.getByLabelText(/Saved only/));
    expect(onChange).toHaveBeenLastCalledWith({ savedOnly: true });

    await user.selectOptions(screen.getByLabelText(/Sort jobs/), "company");
    expect(onChange).toHaveBeenLastCalledWith({ sortBy: "company" });
  });
});
