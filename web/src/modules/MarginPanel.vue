<template>
  <div class="card">
    <h3>
      两融数据
      <StatusBadge :status="module.status" />
    </h3>
    <div v-if="module.status === 'PENDING'" class="notice">
      两融数据 T+1 披露，今日暂缺，待次日回补。
    </div>
    <div class="grid grid-4">
      <div class="metric">
        <div class="label">融资余额</div>
        <div class="value">{{ fmt(module.financingBalance) }}</div>
      </div>
      <div class="metric">
        <div class="label">融券余额</div>
        <div class="value">{{ fmt(module.securitiesLendingBalance) }}</div>
      </div>
      <div class="metric">
        <div class="label">两融总余额</div>
        <div class="value">{{ fmt(module.marginBalance) }}</div>
        <div class="sub" :class="signClass(module.marginBalanceChange)">{{ fmtSigned(module.marginBalanceChange) }}</div>
      </div>
      <div class="metric">
        <div class="label">融资净买入</div>
        <div class="value" :class="signClass(module.financingNetBuyAmount?.value)">
          {{ fmtSigned(module.financingNetBuyAmount?.value) }}
        </div>
        <div class="sub flat">{{ qualityText(module.financingNetBuyAmount?.quality) }}</div>
      </div>
    </div>
    <div class="empty-tip">
      两融成交额：{{ fmt(module.marginTradeAmount?.value) }}（{{ qualityText(module.marginTradeAmount?.quality) }}）· 占比 {{ pct(module.marginTradeSharePct?.value) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import type { MarginModule } from "../types/smi";
import StatusBadge from "../components/StatusBadge.vue";

defineProps<{ module: MarginModule }>();

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)} 亿`;
}

function fmtSigned(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)} 亿`;
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}%`;
}

function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "flat";
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}

function qualityText(q: string | undefined): string {
  if (q === "DERIVED") return "派生计算";
  if (q === "ESTIMATED") return "估算";
  if (q === "LEGACY") return "历史导入";
  return "—";
}
</script>

<style scoped>
.notice {
  background: rgba(66, 165, 245, 0.08);
  border: 1px solid rgba(66, 165, 245, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--blue);
  margin-bottom: 10px;
}
</style>
