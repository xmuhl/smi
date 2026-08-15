import type { ModuleBase, ModuleStatus } from "../types/smi";
import { STATUS_TEXT } from "./format";

export function statusBadge(status: ModuleStatus | undefined): string {
  const s = status ?? "PENDING";
  const meta = STATUS_TEXT[s] ?? STATUS_TEXT.PENDING;
  return `<span class="badge ${meta.cls}">${meta.icon} ${meta.text}</span>`;
}

export function moduleStatusCounts(
  modules: Record<string, ModuleBase>,
): {
  final: number;
  pending: number;
  stale: number;
  partial: number;
  unavailable: number;
  error: number;
  total: number;
} {
  const counts = {
    final: 0,
    pending: 0,
    stale: 0,
    partial: 0,
    unavailable: 0,
    error: 0,
    total: 0,
  };

  for (const module of Object.values(modules)) {
    counts.total += 1;

    if (module.status === "FINAL") {
      counts.final += 1;
    } else if (module.status === "PENDING") {
      counts.pending += 1;
    } else if (module.status === "STALE") {
      counts.stale += 1;
    } else if (module.status === "PARTIAL") {
      counts.partial += 1;
    } else if (module.status === "UNAVAILABLE") {
      counts.unavailable += 1;
    } else if (module.status === "ERROR") {
      counts.error += 1;
    }
  }

  return counts;
}

