"use client";

import { EmptyState } from "@/components/States";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <EmptyState title="Something went wrong">
      <p>The ForeverTracker API could not be reached or returned an error.</p>
      <Button onClick={reset} variant="outline" className="mt-4">
        Try again
      </Button>
    </EmptyState>
  );
}
