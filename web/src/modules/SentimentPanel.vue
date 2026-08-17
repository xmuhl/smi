<template>
  <div class="card">
    <h3>
      市场情绪
      <StatusBadge :status="module.status" />
    </h3>
    <div class="grid grid-3">
      <div class="metric">
        <div class="label">上涨家数</div>
        <div class="value up">{{ module.riseCount ?? "—" }}</div>
        <div class="sub down">下跌 {{ module.fallCount ?? "—" }}</div>
        <div class="sub flat">平盘 {{ module.flatCount ?? "—" }}</div>
      </div>
      <div class="metric">
        <div class="label">非ST涨停</div>
        <div class="value up">{{ module.nonStLimitUpCount ?? "—" }}</div>
        <div class="sub flat">ST涨停 {{ module.stLimitUpCount ?? "—" }}</div>
      </div>
      <div class="metric">
        <div class="label">非ST跌停</div>
        <div class="value down">{{ module.nonStLimitDownCount ?? "—" }}</div>
        <div class="sub flat">ST跌停 {{ module.stLimitDownCount ?? "—" }}</div>
      </div>
    </div>
    <div class="empty-tip" v-if="hasExtra">
      炸板 {{ module.brokenLimitCount ?? "—" }} 家 ·
      涨停封板率 {{ sealRateText }} ·
      最高连板 {{ module.maxLimitUpStreak ?? "—" }}
    </div>
    <div class="boundary-tip" v-if="widthGapNote">
      {{ widthGapNote }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SentimentModule } from "../types/smi";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ module: SentimentModule }>();

// limitSealRatePct / maxLimitUpStreak 已由 snapshot 提供，但类型声明尚未补充，
// 通过 any 取值以避免改动 types 文件
const m = computed(() => props.module as unknown as Record<string, unknown>);

const sealRate = computed(() => m.value.limitSealRatePct as number | null | undefined);

const sealRateText = computed(() => {
  if (sealRate.value === null || sealRate.value === undefined || Number.isNaN(sealRate.value)) {
    return "—";
  }
  return `${sealRate.value}%`;
});

const hasExtra = computed(() => {
  const b = props.module.brokenLimitCount;
  const s = sealRate.value;
  const streak = m.value.maxLimitUpStreak;
  return (
    (b !== null && b !== undefined) ||
    (s !== null && s !== undefined) ||
    (streak !== null && streak !== undefined && streak !== "")
  );
});

// R12 P3-003：历史市场宽度（涨跌家数）无免费历史源时的已知边界提示
const widthGapNote = computed(() => {
  const rc = props.module.riseCount;
  const fc = props.module.fallCount;
  const flat = props.module.flatCount;
  const allNull =
    (rc === null || rc === undefined) &&
    (fc === null || fc === undefined) &&
    (flat === null || flat === undefined);
  if (!allNull) return "";
  const st = props.module.status;
  if (st !== "PARTIAL" && st !== "UNAVAILABLE" && st !== "PENDING") return "";
  return "市场宽度（涨跌家数）无历史源，仅显示可采集指标（历史覆盖 Profile 已知边界）";
});
</script>
