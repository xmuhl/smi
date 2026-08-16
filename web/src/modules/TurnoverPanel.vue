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
    <!-- 跨口径参考：comparisonStatus=PREVIOUS_METHOD_MISMATCH 时渲染结构化 crossMethodReference 块，显著标注不可与正常环比比较（标准 turnover displayRules #2） -->
    <div v-if="crossRef" class="cross-ref">
      <div class="cross-ref-title">跨口径参考（非同一口径，不可与正常环比比较）</div>
      <div class="cross-ref-body">
        前一日 {{ fmtYi(crossRef.previous) }} ·
        增减 {{ fmtSigned(crossRef.delta) }} ·
        幅度 {{ fmtPct(crossRef.changePct) }}
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

// 跨口径结构化块字段不在 TurnoverModule 类型上，这里扩展声明并宽松读取（runtime 数据带有 comparisonStatus/crossMethodReference）
interface CrossMethodReference {
  previous: number;
  delta: number;
  changePct: number;
  nonComparable: boolean;
  currentMethod: string;
  previousMethod: string;
}

const turn = props.module as TurnoverModule & {
  comparisonStatus?: string;
  crossMethodReference?: CrossMethodReference;
};

// 仅当比较状态为跨口径且参考块存在时才展示
const crossRef = computed<CrossMethodReference | null>(() => {
  const m = turn;
  if (m.comparisonStatus !== "PREVIOUS_METHOD_MISMATCH") return null;
  return m.crossMethodReference && m.crossMethodReference.nonComparable ? m.crossMethodReference : null;
});

function fmtYi(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)} 亿`;
}

function fmtSigned(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)} 亿`;
}

const volumeClass = computed(() => {
  const s = props.module.volumeState;
  if (s === "EXPANSION") return "up";
  if (s === "CONTRACTION") return "down";
  return "flat";
});
</script>

<style scoped>
.cross-ref {
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid rgba(255, 193, 7, 0.4);
  border-left: 3px solid var(--yellow);
  border-radius: 8px;
  background: rgba(255, 193, 7, 0.06);
  font-size: 12px;
  color: var(--text);
}
.cross-ref-title {
  color: var(--yellow, #f59e0b);
  font-weight: 600;
  margin-bottom: 4px;
}
.cross-ref-body {
  color: var(--text-dim);
}
</style>
