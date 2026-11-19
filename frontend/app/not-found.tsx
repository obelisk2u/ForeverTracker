import Link from "next/link";

import { EmptyState } from "@/components/States";
import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <EmptyState title="Not found">
      <p>That character or run is not in ForeverTracker. Characters appear once a ForeverTracker user has recorded a run with them.</p>
      <p className="mt-4">
        <Link href="/search" className={buttonVariants({ variant: "outline" })}>
          Search for a character
        </Link>
      </p>
    </EmptyState>
  );
}
