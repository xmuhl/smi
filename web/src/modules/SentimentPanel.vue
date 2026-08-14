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
    <div class="empty-tip" v-if="module.brokenLimitCount !== null && module.brokenLimitCount !== undefined">
      炸板 {{ module.brokenLimitCount }} 家 · 平盘 {{ module.flatCount ?? "—" }} 家
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SentimentModule } from "../types/smi";
import StatusBadge from "../components/StatusBadge.vue";

defineProps<{ module: SentimentModule }>();
</script>
