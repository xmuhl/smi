<template>
  <div class="card">
    <h3>
      宽基指数
      <StatusBadge :status="module.status" />
    </h3>
    <div class="grid grid-4">
      <div v-for="it in items" :key="it.code || it.name" class="metric">
        <div class="label">{{ it.name }}</div>
        <div class="value">{{ fmt(it.close) }}</div>
        <div class="sub" :class="pctClass(it.changePct)">{{ fmtPct(it.changePct) }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { MarketIndexModule } from "../types/smi";
import { fmtNum, fmtPct, pctClass } from "../utils/format";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ module: MarketIndexModule }>();

const items = computed(() => (props.module.items ?? []).filter((it) => it.name && it.name !== "nan"));

function fmt(v: number | null): string {
  return fmtNum(v, 2);
}
</script>
