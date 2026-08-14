import { ref, type Ref } from "vue";
import type { DailySnapshot, Manifest } from "../types/smi";
import { loadDaily, loadManifest } from "../utils/format";

export function useManifest() {
  const manifest = ref<Manifest | null>(null);
  const manifestError = ref<string>("");

  async function refresh() {
    manifestError.value = "";
    try {
      manifest.value = await loadManifest();
    } catch (e) {
      manifestError.value = e instanceof Error ? e.message : String(e);
    }
  }

  return { manifest, manifestError, refresh };
}

export function useDailySnapshot() {
  const snapshot = ref<DailySnapshot | null>(null);
  const loading = ref(false);
  const error = ref<string>("");

  async function load(date: string) {
    loading.value = true;
    error.value = "";
    try {
      snapshot.value = await loadDaily(date);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      snapshot.value = null;
    } finally {
      loading.value = false;
    }
  }

  return { snapshot, loading, error, load };
}
