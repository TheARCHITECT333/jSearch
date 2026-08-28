import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchButton } from "../src/components/SearchButton";

describe("SearchButton", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders the freshness selector with all windows", () => {
    render(
      <SearchButton
        disabledReasons={[]}
        running={false}
        freshness="1w"
        onFreshnessChange={vi.fn()}
        onStart={vi.fn()}
      />
    );
    const select = screen.getByTestId("freshness-select") as HTMLSelectElement;
    expect(select.value).toBe("1w");
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(["any", "24h", "3d", "1w", "2w", "1m"]);
    expect(screen.getByRole("option", { name: "Last 24 hours" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Last week" })).toBeInTheDocument();
  });

  it("emits the chosen window", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <SearchButton
        disabledReasons={[]}
        running={false}
        freshness="any"
        onFreshnessChange={onChange}
        onStart={vi.fn()}
      />
    );
    await user.selectOptions(screen.getByTestId("freshness-select"), "24h");
    expect(onChange).toHaveBeenCalledWith("24h");
  });

  it("disables both button and selector while a search runs", () => {
    render(
      <SearchButton
        disabledReasons={[]}
        running={true}
        freshness="24h"
        onFreshnessChange={vi.fn()}
        onStart={vi.fn()}
      />
    );
    expect(screen.getByTestId("find-jobs-button")).toBeDisabled();
    expect(screen.getByTestId("freshness-select")).toBeDisabled();
    expect(screen.getByText(/Searching\.\.\./)).toBeInTheDocument();
  });

  it("lists validation reasons and disables the button", () => {
    render(
      <SearchButton
        disabledReasons={["Load your resume first.", "Enable at least one company."]}
        running={false}
        freshness="1w"
        onFreshnessChange={vi.fn()}
        onStart={vi.fn()}
      />
    );
    expect(screen.getByTestId("find-jobs-button")).toBeDisabled();
    expect(screen.getByTestId("disabled-reasons")).toHaveTextContent(
      "Load your resume first."
    );
  });

  it("starts a search when enabled", async () => {
    const onStart = vi.fn();
    const user = userEvent.setup();
    render(
      <SearchButton
        disabledReasons={[]}
        running={false}
        freshness="2w"
        onFreshnessChange={vi.fn()}
        onStart={onStart}
      />
    );
    await user.click(screen.getByTestId("find-jobs-button"));
    expect(onStart).toHaveBeenCalledTimes(1);
  });
});
