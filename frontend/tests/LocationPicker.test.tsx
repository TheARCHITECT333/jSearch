import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocationPicker } from "../src/components/LocationPicker";

describe("LocationPicker", () => {
  beforeEach(() => window.localStorage.clear());

  it("shows the anywhere mode when no locations are set", () => {
    render(<LocationPicker locations={[]} onChange={vi.fn()} />);
    expect(screen.getByTestId("location-mode")).toHaveTextContent(
      "searching anywhere"
    );
    expect(screen.getByTestId("location-input")).toHaveAttribute(
      "placeholder",
      expect.stringContaining("Bangalore")
    );
  });

  it("adds a location on Enter and shows a chip", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<LocationPicker locations={[]} onChange={onChange} />);

    const input = screen.getByTestId("location-input");
    await user.type(input, "Bangalore{Enter}");

    expect(onChange).toHaveBeenCalledWith(["Bangalore"]);
  });

  it("adds on comma and trims trailing commas / whitespace", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<LocationPicker locations={[]} onChange={onChange} />);

    await user.type(screen.getByTestId("location-input"), "  Remote ,");
    expect(onChange).toHaveBeenCalledWith(["Remote"]);
  });

  it("does not add duplicates (case-insensitive)", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<LocationPicker locations={["Bangalore"]} onChange={onChange} />);

    await user.type(screen.getByTestId("location-input"), "bangalore{Enter}");
    expect(onChange).not.toHaveBeenCalledWith(["Bangalore", "bangalore"]);
    // Duplicate add is silently ignored (no change emitted at all).
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes chips via their ✕ button", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LocationPicker
        locations={["Bangalore", "Remote"]}
        onChange={onChange}
      />
    );

    expect(screen.getByTestId("location-mode")).toHaveTextContent(
      "only 2 locations"
    );
    await user.click(screen.getByLabelText("Remove Bangalore"));
    expect(onChange).toHaveBeenCalledWith(["Remote"]);
  });

  it("Backspace on empty input removes the last chip", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<LocationPicker locations={["Pune"]} onChange={onChange} />);

    const input = screen.getByTestId("location-input");
    await user.click(input);
    await user.keyboard("{Backspace}");
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("commits the draft when the input loses focus", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<LocationPicker locations={[]} onChange={onChange} />);

    await user.type(screen.getByTestId("location-input"), "Hyderabad");
    await user.tab(); // blur
    expect(onChange).toHaveBeenCalledWith(["Hyderabad"]);
  });
});
