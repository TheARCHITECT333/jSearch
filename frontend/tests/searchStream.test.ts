/**
 * SSE subscription behaviour: which frames close the stream, and when the
 * caller is told to fall back to polling.
 *
 * jsdom has no EventSource, so a minimal fake stands in - it only needs to
 * dispatch the events the real one would.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { streamSearchProgress } from "../src/api/search";
import type { SearchStatus } from "../src/types/search";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  url: string;
  closed = false;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Array<() => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: () => void) {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, [...existing, handler]);
  }

  close() {
    this.closed = true;
  }

  emit(status: Partial<SearchStatus>) {
    this.onmessage?.({
      data: JSON.stringify({
        id: "s1",
        companies: [],
        results: [],
        error: null,
        ...status,
      }),
    });
  }

  emitNamed(type: string) {
    for (const handler of this.listeners.get(type) ?? []) handler();
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function subscribe() {
  const onUpdate = vi.fn();
  const onFallback = vi.fn();
  const close = streamSearchProgress("s1", { onUpdate, onFallback });
  const source = FakeEventSource.instances[0];
  return { onUpdate, onFallback, close, source };
}

describe("streamSearchProgress", () => {
  it("forwards running frames without closing the stream", () => {
    const { onUpdate, source } = subscribe();

    source.emit({ status: "running" });

    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate.mock.calls[0][0].status).toBe("running");
    expect(source.closed).toBe(false);
  });

  it.each(["completed", "failed", "cancelled"] as const)(
    "delivers the %s frame and then closes",
    (status) => {
      const { onUpdate, onFallback, source } = subscribe();

      source.emit({ status });

      // The terminal frame itself must reach the caller - a cancelled search
      // that never renders leaves the UI stuck on stale progress.
      expect(onUpdate).toHaveBeenCalledTimes(1);
      expect(onUpdate.mock.calls[0][0].status).toBe(status);
      expect(source.closed).toBe(true);

      // A clean close after a terminal frame is not a failure.
      source.onerror?.();
      expect(onFallback).not.toHaveBeenCalled();
    }
  );

  it("falls back to polling when the stream dies before any frame", () => {
    const { onFallback, source } = subscribe();

    source.onerror?.();

    expect(onFallback).toHaveBeenCalledTimes(1);
    expect(source.closed).toBe(true);
  });

  it("falls back to polling when the stream drops mid-search", () => {
    const { onFallback, source } = subscribe();

    source.emit({ status: "running" });
    source.onerror?.();

    expect(onFallback).toHaveBeenCalledTimes(1);
  });

  it("falls back to polling when the server reports the search is gone", () => {
    const { onFallback, source } = subscribe();

    source.emitNamed("gone");

    expect(source.closed).toBe(true);
    expect(onFallback).toHaveBeenCalledTimes(1);
  });

  it("ignores malformed frames instead of throwing", () => {
    const { onUpdate, source } = subscribe();

    expect(() => source.onmessage?.({ data: "not json" })).not.toThrow();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("close() shuts the stream down", () => {
    const { close, source } = subscribe();

    close();

    expect(source.closed).toBe(true);
  });
});
