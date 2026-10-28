import { api } from "@/lib/api";

// Shown whenever the API reports simulator-generated data. Production refuses such data
// entirely, so this banner can never appear on real histories.
export async function SyntheticBanner() {
  let present = false;
  let environment = "";
  try {
    const meta = await api.meta();
    present = meta.synthetic_data_present;
    environment = meta.environment;
  } catch {
    return null;
  }
  if (!present) return null;
  return (
    <div role="status" className="bg-warn/15 border-b border-warn/40 text-warn text-sm">
      <div className="mx-auto max-w-6xl px-4 py-2">
        <strong>Development data.</strong> This {environment} site contains synthetic characters and runs generated
        by the ForeverTracker simulator. None of it describes real players.
      </div>
    </div>
  );
}
