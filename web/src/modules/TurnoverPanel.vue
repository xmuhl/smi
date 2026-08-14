<template>
  <div class="card">
    <h3>
      两市成交额
      <StatusBadge :status="module.status" />
    </h3>
    <div class="grid grid-4">
      <div class="metric">
        <div class="label">当日合计</div>
        <div class="value">{{ fmtYi(module.turnoverToday) }}</div>
        <div class="sub flat">沪市+深市</div>
      </div>
      <div class="metric">
        <div class="label">前一交易日</div>
        <div class="value">{{ fmtYi(module.turnoverPrevious) }}</div>
        <div class="sub flat">上一有效交易日快照</div>
      </div>
      <div class="metric">
        <div class="label">增减金额</div>
        <div class="value" :class="pctClass(module.turnoverDelta)">{{ fmtYi(module.turnoverDelta) }}</div>
        <div class="sub" :class="pctClass(module.turnoverChangePct)">{{ fmtPct(module.turnoverChangePct) }}</div>
      </div>
      <div class="metric">
        <div class="label">量能定性</div>
        <div class="value" :class="volumeClass">{{ volumeStateText(module.volumeState) }}</div>
        <div class="sub flat">放量/缩量/平量</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { TurnoverModule } from "../types/smi";
import { fmtPct, pctClass, volumeStateText } from "../utils/format";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ module: TurnoverModule }>();

function fmtYi(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)} 亿`;
}

const volumeClass = computed(() => {
  const s = props.module.volumeState;
  if (s === "EXPANSION") return "up";
  if (s === "CONTRACTION") return "down";
  return "flat";
});
</script>
