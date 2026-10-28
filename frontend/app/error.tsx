"use client";

import { EmptyState } from "@/components/States";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <EmptyState title="Something went wrong">
      <p>The ForeverTracker API could not be reached or returned an error.</p>
      <button onClick={reset} className="mt-3 px-4 py-2 rounded-lg border border-line hover:bg-surface-2">
        Try again
      </button>
    </EmptyState>
  );
}
