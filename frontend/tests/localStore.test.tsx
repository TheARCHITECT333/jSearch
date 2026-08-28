import { beforeEach, describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { store, useAppState } from "../src/storage/localStore";

describe("localStore", () => {
  beforeEach(() => window.localStorage.clear());

  it("persists state to localStorage and reads it back", () => {
    const { result } = renderHook(() => useAppState());
    expect(result.current[0].companies).toEqual([]);

    act(() => {
      store.set({
        companies: [{ name: "Stripe", careers_url: "https://stripe.com/jobs" }],
      });
    });

    expect(
      JSON.parse(window.localStorage.getItem("jobhunter.companies")!)
    ).toEqual([{ name: "Stripe", careers_url: "https://stripe.com/jobs" }]);
    expect(store.get().companies).toHaveLength(1);
  });

  it("never persists an API key (no such storage key exists)", () => {
    const { result } = renderHook(() => useAppState());
    act(() => {
      store.set({
        llmProvider: "openai-compatible",
        llmBaseUrl: "https://api.example.com/v1",
        llmModel: "gpt-4o-mini",
      });
    });

    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i);
      expect(key?.toLowerCase()).not.toContain("apikey");
    }
    // And the state shape itself has no api key field.
    expect(Object.keys(result.current[0])).not.toContain("apiKey");
  });

  it("notifies subscribers on change", () => {
    const seen: number[] = [];
    const unsubscribe = store.subscribe(() => seen.push(store.get().companies.length));

    act(() => {
      store.set({ companies: [{ name: "A", careers_url: "https://a.example/jobs" }] });
    });
    unsubscribe();
    act(() => {
      store.set({ companies: [] });
    });

    expect(seen).toEqual([1]); // unsubscribed before second change
  });

  it("tolerates corrupted stored JSON", () => {
    window.localStorage.setItem("jobhunter.latestResults", "{not json");
    const { result } = renderHook(() => useAppState());
    expect(result.current[0].latestResults).toEqual([]);
  });
});
