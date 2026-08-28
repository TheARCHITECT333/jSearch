import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CompanyList } from "../src/components/CompanyList";
import type { Company } from "../src/types/company";

const companies: Company[] = [
  { name: "Google", careers_url: "https://careers.google.com/jobs/results/" },
  { name: "Stripe", careers_url: "https://stripe.com/jobs" },
];

describe("CompanyList", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("prompts for import when no companies exist", () => {
    render(
      <CompanyList
        companies={[]}
        enabled={{}}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={vi.fn()}
        onClear={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.getByText(/Import a/i)).toBeInTheDocument();
    expect(
      screen.getByTestId("import-companies-button")
    ).toBeInTheDocument();
  });

  it("renders companies with enabled state and toggles them", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CompanyList
        companies={companies}
        enabled={{ Google: true, Stripe: false }}
        onChangeEnabled={onChange}
        onSetAllEnabled={vi.fn()}
        onClear={vi.fn()}
        onImport={vi.fn()}
      />
    );

    expect(screen.getByText(/Google/)).toBeInTheDocument();
    expect(screen.getByText(/Stripe/)).toBeInTheDocument();

    const googleCheckbox = screen.getByLabelText("Enable Google") as HTMLInputElement;
    const stripeCheckbox = screen.getByLabelText("Enable Stripe") as HTMLInputElement;
    expect(googleCheckbox.checked).toBe(true);
    expect(stripeCheckbox.checked).toBe(false);

    await user.click(stripeCheckbox);
    expect(onChange).toHaveBeenCalledWith("Stripe", true);
  });

  it("imports valid JSON via the hidden file input", async () => {
    const onImport = vi.fn();
    render(
      <CompanyList
        companies={[]}
        enabled={{}}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={vi.fn()}
        onClear={vi.fn()}
        onImport={onImport}
      />
    );

    const input = screen.getByTestId("companies-file-input");
    const file = new File(
      [JSON.stringify(companies)],
      "companies.json",
      { type: "application/json" }
    );
    await userEvent.upload(input, file);

    expect(onImport).toHaveBeenCalledWith(
      [
        { name: "Google", careers_url: "https://careers.google.com/jobs/results/" },
        { name: "Stripe", careers_url: "https://stripe.com/jobs" },
      ],
      []
    );
  });

  it("reports validation errors for invalid entries", async () => {
    const onImport = vi.fn();
    render(
      <CompanyList
        companies={[]}
        enabled={{}}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={vi.fn()}
        onClear={vi.fn()}
        onImport={onImport}
      />
    );

    const input = screen.getByTestId("companies-file-input");
    const badFile = new File(
      [JSON.stringify([{ name: "", careers_url: "not-a-url" }])],
      "companies.json",
      { type: "application/json" }
    );
    await userEvent.upload(input, badFile);

    expect(onImport).toHaveBeenCalledWith([], [
      expect.stringContaining('"name" is required'),
      expect.stringContaining("valid HTTP/HTTPS URL"),
    ]);
  });

  it("enables every company at once", async () => {
    const onSetAllEnabled = vi.fn();
    const user = userEvent.setup();
    render(
      <CompanyList
        companies={companies}
        enabled={{ Google: true, Stripe: false }}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={onSetAllEnabled}
        onClear={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId("select-all-companies"));
    // One bulk call, not one per company: separate per-company calls would
    // each read the same state snapshot and clobber one another.
    expect(onSetAllEnabled).toHaveBeenCalledTimes(1);
    expect(onSetAllEnabled).toHaveBeenCalledWith(true);
  });

  it("disables every company at once", async () => {
    const onSetAllEnabled = vi.fn();
    const user = userEvent.setup();
    render(
      <CompanyList
        companies={companies}
        enabled={{ Google: true, Stripe: true }}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={onSetAllEnabled}
        onClear={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId("unselect-all-companies"));
    expect(onSetAllEnabled).toHaveBeenCalledWith(false);
  });

  it("does not offer bulk toggles when there is nothing to toggle", () => {
    render(
      <CompanyList
        companies={[]}
        enabled={{}}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={vi.fn()}
        onClear={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.queryByTestId("select-all-companies")).not.toBeInTheDocument();
    expect(screen.queryByTestId("clear-companies-button")).not.toBeInTheDocument();
  });

  it("asks before deleting the list", async () => {
    const onClear = vi.fn();
    const user = userEvent.setup();
    render(
      <CompanyList
        companies={companies}
        enabled={{}}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={vi.fn()}
        onClear={onClear}
        onImport={vi.fn()}
      />
    );
    // Deleting throws away an import, so the first click only arms it.
    await user.click(screen.getByTestId("clear-companies-button"));
    expect(onClear).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("confirm-clear-companies"));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("lets you back out of deleting the list", async () => {
    const onClear = vi.fn();
    const user = userEvent.setup();
    render(
      <CompanyList
        companies={companies}
        enabled={{}}
        onChangeEnabled={vi.fn()}
        onSetAllEnabled={vi.fn()}
        onClear={onClear}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId("clear-companies-button"));
    await user.click(screen.getByTestId("cancel-clear-companies"));
    expect(onClear).not.toHaveBeenCalled();
    expect(screen.getByTestId("clear-companies-button")).toBeInTheDocument();
  });
});
