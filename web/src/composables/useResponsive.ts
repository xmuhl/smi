import { computed } from "vue";
import type { ModuleBase, ModuleStatus } from "../types/smi";

export function useResponsive() {
  return { isMobile: computed(() => false) };
}

export type { ModuleBase, ModuleStatus };
