// Truthful health derivation for the dashboard.
//
// A status is only "healthy" when a fresh observation says so. Missing,
// stale or unrecognised observations degrade to "unknown"/"stale" — never
// to a green label.

export type OverallHealth = "operational" | "degraded" | "unavailable" | "stale" | "unknown";

export interface ObservedStatus {
  observed_at?: string | null;
  api_health?: string | null;
  rate_limits?: string | null;
  crisis_state?: string | null;
}

export const STALE_AFTER_MS = 60_000;

const HEALTHY = new Set(["healthy", "good"]);
const DEGRADED = new Set(["degraded", "warning"]);
const DOWN = new Set(["unavailable", "error", "failed"]);

export function deriveOverallHealth(
  status: ObservedStatus | null | undefined,
  nowMs: number,
  staleAfterMs: number = STALE_AFTER_MS,
): OverallHealth {
  if (!status || !status.observed_at) return "unknown";
  const observed = Date.parse(status.observed_at);
  if (Number.isNaN(observed)) return "unknown";
  if (nowMs - observed > staleAfterMs) return "stale";

  const parts = [status.api_health, status.rate_limits].map((v) => (v ?? "").toLowerCase());
  if (parts.some((v) => DOWN.has(v))) return "unavailable";
  if (parts.some((v) => !HEALTHY.has(v) && !DEGRADED.has(v))) return "unknown";
  if (parts.some((v) => DEGRADED.has(v))) return "degraded";
  if ((status.crisis_state ?? "").toUpperCase() !== "NORMAL") return "degraded";
  return "operational";
}

export const OVERALL_HEALTH_LABEL: Record<OverallHealth, string> = {
  operational: "All observed systems operational",
  degraded: "Degraded",
  unavailable: "Dependency unavailable",
  stale: "Status stale",
  unknown: "Status unknown",
};
