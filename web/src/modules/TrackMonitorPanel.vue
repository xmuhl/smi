<template>
  <div class="card">
    <h3>
      主赛道每日监测
      <StatusBadge :status="module.status" />
    </h3>
    <div class="table-wrap">
      <table class="smi-table track-table">
        <tr>
          <th>监测日期</th>
          <th>板块名称</th>
          <th>板块定位</th>
          <th>近5日成交额排名</th>
          <th>今日主力净流入(亿)</th>
          <th>连续净流入天数</th>
          <th>5-10-20日多头排列</th>
          <th>60日RPS数值</th>
          <th>近10日跑赢沪深300</th>
          <th>板块涨停家数</th>
          <th>连板梯队完整度</th>
          <th>红盘个股占比</th>
          <th>核心催化逻辑</th>
          <th>业绩兑现情况</th>
          <th>综合达标率</th>
          <th>最终判定</th>
        </tr>
        <tr v-for="it in module.items" :key="it.trackId">
          <td>{{ it.date ?? "—" }}</td>
          <td>{{ it.trackName }}</td>
          <td class="dim">{{ it.positioning }}</td>
          <td>{{ it.turnoverRank ?? "—" }}</td>
          <td :class="signClass(it.mainNetInflow)">{{ fmtYi(it.mainNetInflow) }}</td>
          <td>{{ it.continuousInflowDays ?? "—" }}日</td>
          <td>{{ it.maAlignment ?? "—" }}</td>
          <td>{{ it.rps60 ?? "—" }}</td>
          <td>{{ it.excessReturn20d ?? "—" }}</td>
          <td>{{ it.limitUpCount ?? "—" }}</td>
          <td>{{ it.ladderCompleteness ?? "—" }}</td>
          <td>{{ it.redStockRatio ?? "—" }}</td>
          <td>{{ it.coreCatalyst ?? "—" }}</td>
          <td>{{ it.earningsRealization ?? "—" }}</td>
          <td><b>{{ it.score ?? "—" }}</b></td>
          <td :class="decisionClass(it.decision)"><b>{{ decisionText(it.decision) }}</b></td>
        </tr>
        <tr v-if="!module.items.length"><td colspan="16" class="empty-tip">暂无赛道数据</td></tr>
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
