<template>
  <div class="card">
    <h3>
      主赛道每日监测
      <StatusBadge :status="module.status" />
    </h3>
    <div class="table-wrap">
      <table class="smi-table track-table">
        <tr>
          <th>赛道</th>
          <th>定位</th>
          <th>主力净流入</th>
          <th>连流入</th>
          <th>RPS60</th>
          <th>涨停</th>
          <th>综合分</th>
          <th>判定</th>
        </tr>
        <tr v-for="it in module.items" :key="it.trackId">
          <td>{{ it.trackName }}</td>
          <td class="dim">{{ it.positioning }}</td>
          <td :class="signClass(it.mainNetInflow)">{{ fmtYi(it.mainNetInflow) }}</td>
          <td>{{ it.continuousInflowDays ?? "—" }}日</td>
          <td>{{ it.rps60 ?? "—" }}</td>
          <td>{{ it.limitUpCount ?? "—" }}</td>
          <td><b>{{ it.score ?? "—" }}</b></td>
          <td :class="decisionClass(it.decision)"><b>{{ decisionText(it.decision) }}</b></td>
        </tr>
        <tr v-if="!module.items.length"><td colspan="8" class="empty-tip">暂无赛道数据</td></tr>
      </table>
    </div>
    <div class="empty-tip" v-if="module.sourceSystem === 'TONGDAXIN_LEGACY'">
      数据口径：通达信 Legacy（历史导入）
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TracksModule } from "../types/smi";
import { decisionClass, decisionText } from "../utils/format";
import StatusBadge from "../components/StatusBadge.vue";

defineProps<{ module: TracksModule }>();

function fmtYi(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}亿`;
}

function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "flat";
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}
</script>

<style scoped>
.table-wrap {
  overflow-x: auto;
}
.track-table th,
.track-table td {
  white-space: nowrap;
}
.dim {
  color: var(--text-dim);
  font-size: 12px;
}
</style>
