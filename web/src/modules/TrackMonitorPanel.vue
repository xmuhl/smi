<template>
  <div class="card">
    <h3>
      主赛道每日监测
      <StatusBadge :status="module.status" />
    </h3>
    <!-- UI 评审 B3：覆盖/降级/预热说明上移到表格之前，先读语义再看数据 -->
    <div class="boundary-tip" v-if="unavailableNote">
      {{ unavailableNote }}
    </div>
    <div class="boundary-tip" v-if="degradedNote">
      {{ degradedNote }}
    </div>
    <div class="boundary-tip" v-if="warmingNote">
      {{ warmingNote }}
    </div>
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
          <td>
            {{ it.trackName }}
            <span v-if="it.poolQualification === 'RETAINED_OBSERVATION'"
              class="badge-warming"
              title="迟滞观察保留：曾满足范本资格（近5日成交额前5），当前排名跌出前5但未满出池确认（连续2日跌出前12），继续观察而非当日入选">观察保留</span>
          </td>
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
          <td>
            <b>{{ it.score ?? "—" }}</b>
            <span v-if="it.dataReadiness === 'WARMING_UP'" class="badge-warming"
              :title="`冷启动预热中：close 历史 ${it.historyDays ?? 0} 日，未达 minHistoryDays 就绪线，不参与正式评分`">预热</span>
          </td>
          <td :class="decisionClass(it.decision)">
            <b>{{ it.dataReadiness === 'WARMING_UP' ? "预热中" : decisionText(it.decision) }}</b>
          </td>
        </tr>
        <tr v-if="!module.items.length"><td colspan="16" class="empty-tip">{{ emptyText }}</td></tr>
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

const props = defineProps<{ module: TracksModule; tradeDate?: string }>();

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

import { computed } from "vue";

// R23-P3-01：空表必须区分两种事实——上游不可用（无法判断）与
// 数据完整但无合格板块（市场无主线），不得共用一句"暂无赛道数据"
const emptyText = computed(() => {
  if (props.module.status === "UNAVAILABLE") {
    return "上游赛道数据暂不可用（板块快照缺失或未过完整性校验），无法判断当日主线";
  }
  return "今日暂无符合筛选条件的主赛道（监测口径前5：行业板块全景 + 已配置概念赛道联合排名）";
});

// R12 P3-003：历史量化输入底座不足的已知边界提示
const unavailableNote = computed(() => {
  if (props.module.status !== "UNAVAILABLE") return "";
  const td = props.tradeDate || "";
  if (td && (td < "2026-07-20" || td > "2026-08-14")) return "";
  return "赛道量化指标历史不可用（输入底座不足），仅展示可用归档数据（历史覆盖 Profile 已知边界）";
});

// R14-P3-01：TRACKS_DEGRADED（coverage 降置信区间）与 WARMING_UP 展示映射
const degradedNote = computed(() => {
  if (props.module.decision !== "TRACKS_DEGRADED") return "";
  const cov = props.module.coveragePct;
  const floor = props.module.coverageHardFloorPct;
  const target = props.module.coverageTargetPct;
  return `赛道覆盖率 ${cov ?? "—"}% 处于降级区间 [${floor ?? "—"}, ${target ?? "—"})，` +
    "评分保留但降置信（TRACKS_DEGRADED，不点亮 D0 完整性）";
});

const warmingNote = computed(() => {
  const boards = props.module.warmingUpBoards;
  if (!boards || !boards.length) return "";
  return `冷启动预热中（历史未达就绪线，不参与正式评分）：${boards.join("、")}`;
});
</script>

<style scoped>
.table-wrap {
  overflow-x: auto;
}
.track-table th,
.track-table td {
  white-space: nowrap;
}
/* UI 评审 B3（产品裁决 2026-08-23）：fixed 窄列布局下表头换行、催化/业绩长文本列换行，防溢出重叠 */
.track-table th {
  white-space: normal;
}
.track-table td:nth-child(13),
.track-table td:nth-child(14) {
  white-space: normal;
  word-break: break-word;
}
.badge-warming {
  display: inline-block;
  margin-left: 4px;
  padding: 0 6px;
  border-radius: 8px;
  font-size: 11px;
  line-height: 16px;
  color: #b45309;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.4);
  vertical-align: middle;
}
.dim {
  color: var(--text-dim);
  font-size: 12px;
}
</style>
