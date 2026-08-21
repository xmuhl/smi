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

  // R13-P3-05：请求序列保护——只有最后一次 load() 允许提交状态，
  // 防止快速切换日期时较慢的旧请求覆盖新请求结果。
  let requestSequence = 0;

  async function load(date: string) {
    const requestId = ++requestSequence;

    loading.value = true;
    error.value = "";

    try {
      const nextSnapshot = await loadDaily(date);

      if (requestId !== requestSequence) {
        return;
      }

      snapshot.value = nextSnapshot;
    } catch (e) {
      if (requestId !== requestSequence) {
        return;
      }

      error.value = e instanceof Error ? e.message : String(e);
      snapshot.value = null;
    } finally {
      if (requestId === requestSequence) {
        loading.value = false;
      }
    }
  }

  return { snapshot, loading, error, load };
}
