<template>
  <div>
    <div class="header-bar">
      <div class="logo">SMI <span>·</span> A股收盘全景</div>
      <div class="date-nav">
        <button :disabled="!prevDate" @click="goTo(prevDate)">◀ 前一交易日</button>
        <select :value="currentDate" @change="onSelect">
          <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
        </select>
        <button @click="goTo(latestDate)">最新</button>
        <button :disabled="!nextDate" @click="goTo(nextDate)">后一交易日 ▶</button>
      </div>
      <div class="status-line" v-if="snapshot">
        {{ statusSummary }} · 更新于 {{ snapshot.updatedAt || snapshot.generatedAt || "—" }}
      </div>
      <div class="completeness-line" v-if="manifest">
        采集 {{ manifest.latestCapturedDate || manifest.latestDate || "—" }}
        · 收盘完整 {{ manifest.latestCloseCompleteDate || "—" }}
        · 全量最终 {{ manifest.latestFinalDate || "—" }}
      </div>
    </div>

    <div v-if="error" class="empty-tip">加载失败：{{ error }}</div>
    <div v-else-if="!snapshot" class="empty-tip">加载中…</div>

    <template v-else>
      <div class="legacy-banner" v-if="snapshot.meta.legacy">
        历史 Legacy 数据：来自 {{ snapshot.tradeDate }} 原 Excel（通达信口径），仅用于还原当日报表。
      </div>

      <div class="section-title">① 市场总览</div>
      <div class="grid">
        <MarketIndexPanel :module="snapshot.modules.marketIndex" />
        <div class="grid grid-2">
          <TurnoverPanel :module="snapshot.modules.turnover" />
          <SentimentPanel :module="snapshot.modules.sentiment" />
        </div>
      </div>

      <div class="section-title">② 板块与资金</div>
      <div class="grid grid-3">
        <SectorPanel :module="snapshot.modules.sectorPerformance" />
        <FundFlowPanel :module="snapshot.modules.fundFlow" />
        <NorthboundPanel :module="snapshot.modules.northbound" />
      </div>

      <div class="section-title">③ 杠杆与主赛道</div>
      <div class="grid">
        <MarginPanel :module="snapshot.modules.margin" />
        <TrackMonitorPanel :module="snapshot.modules.tracks" />
      </div>

      <div class="section-title">④ 今日结论</div>
      <SummaryPanel :module="snapshot.modules.summary" />

      <div class="empty-tip" style="margin-top: 24px; text-align: center">
        本数据仅供参考，不构成投资建议 · SMI Stock Market Intelligence
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { DailySnapshot, Manifest } from "./types/smi";
import { loadDaily, loadManifest, volumeStateText } from "./utils/format";
import MarketIndexPanel from "./modules/MarketIndexPanel.vue";
import TurnoverPanel from "./modules/TurnoverPanel.vue";
import SentimentPanel from "./modules/SentimentPanel.vue";
import SectorPanel from "./modules/SectorPanel.vue";
import FundFlowPanel from "./modules/FundFlowPanel.vue";
import NorthboundPanel from "./modules/NorthboundPanel.vue";
import MarginPanel from "./modules/MarginPanel.vue";
import TrackMonitorPanel from "./modules/TrackMonitorPanel.vue";
import SummaryPanel from "./modules/SummaryPanel.vue";

const manifest = ref<Manifest | null>(null);
const snapshot = ref<DailySnapshot | null>(null);
const currentDate = ref("");
const error = ref("");

const dates = computed(() => manifest.value?.availableDates ?? []);
const latestDate = computed(() => manifest.value?.latestCapturedDate || manifest.value?.latestDate || "");

const idx = computed(() => dates.value.indexOf(currentDate.value));
const prevDate = computed(() => (idx.value > 0 ? dates.value[idx.value - 1] : null));
const nextDate = computed(() => (idx.value >= 0 && idx.value < dates.value.length - 1 ? dates.value[idx.value + 1] : null));

const statusSummary = computed(() => {
  if (!snapshot.value) return "";

  const values = Object.values(snapshot.value.modules);

  const statuses = ["FINAL", "PENDING", "STALE", "PARTIAL", "UNAVAILABLE", "ERROR"] as const;

  return statuses
    .map((status) => {
      const count = values.filter((module) => module.status === status).length;
      return count > 0 ? `${count} ${status}` : null;
    })
    .filter((value): value is string => value !== null)
    .join(" · ");
});

async function load(date: string) {
  if (!date) return;
  currentDate.value = date;
  const url = new URL(window.location.href);
  url.searchParams.set("date", date);
  window.history.replaceState({}, "", url.toString());
  try {
    snapshot.value = await loadDaily(date);
    error.value = "";
  } catch (e) {
    snapshot.value = null;
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function goTo(date: string | null) {
  if (date) load(date);
}

function onSelect(e: Event) {
  const target = e.target as HTMLSelectElement;
  load(target.value);
}

onMounted(async () => {
  try {
    manifest.value = await loadManifest();
    const urlDate = new URL(window.location.href).searchParams.get("date");
    const initial = urlDate && dates.value.includes(urlDate) ? urlDate : latestDate.value;
    await load(initial);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});

watch(latestDate, (d) => {
  if (d && !currentDate.value) load(d);
});
</script>

<style scoped>
.completeness-line {
  font-size: 12px;
  color: var(--muted, #999);
  margin-top: 4px;
}
.legacy-banner {
  background: rgba(255, 202, 40, 0.08);
  border: 1px solid rgba(255, 202, 40, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12.5px;
  color: var(--yellow);
  margin: 12px 0;
}
</style>
