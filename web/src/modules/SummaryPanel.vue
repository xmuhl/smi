<template>
  <div class="card">
    <h3>
      综合总结
      <StatusBadge :status="module.status" />
    </h3>
    <div class="summary-block">
      <div class="label">指数与量能</div>
      {{ module.indexAndTurnover }}
    </div>
    <div class="summary-block">
      <div class="label">市场情绪</div>
      {{ module.sentiment }}
    </div>
    <div class="summary-block">
      <div class="label">资金流向</div>
      {{ module.fundFlow }}
    </div>
    <div class="summary-block" v-if="module.margin">
      <div class="label">两融</div>
      {{ module.margin }}
    </div>
    <div class="summary-block">
      <div class="label">赛道监测</div>
      {{ module.trackConclusion }}
    </div>
    <div class="summary-block" v-if="module.northbound">
      <div class="label">北向资金</div>
      {{ module.northbound }}
    </div>
    <div class="summary-block" v-if="module.marketEnvironment">
      <div class="label">市场环境</div>
      {{ module.marketEnvironment }}
    </div>
    <div class="summary-block risk">
      <div class="label">风险提示</div>
      {{ module.riskWarning }}
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SummaryModule } from "../types/smi";
import StatusBadge from "../components/StatusBadge.vue";

defineProps<{ module: SummaryModule }>();
</script>

<style scoped>
.risk {
  border-left-color: var(--yellow);
}
</style>
