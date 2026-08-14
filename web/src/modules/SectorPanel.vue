<template>
  <div class="card">
    <h3>
      板块行情
      <StatusBadge :status="module.status" />
    </h3>
    <div class="tabs">
      <button :class="{ active: tab === 'industry' }" @click="tab = 'industry'">行业板块</button>
      <button :class="{ active: tab === 'concept' }" @click="tab = 'concept'">概念板块</button>
    </div>
    <div class="dual">
      <div>
        <div class="mini-title up">涨幅榜 TOP5</div>
        <table class="smi-table">
          <tr v-for="it in upList" :key="it.name">
            <td>{{ it.name }}</td>
            <td :class="pctClass(it.changePct)">{{ fmtPct(it.changePct) }}</td>
          </tr>
          <tr v-if="!upList.length"><td class="empty-tip">暂无数据</td></tr>
        </table>
      </div>
      <div>
        <div class="mini-title down">跌幅榜 TOP5</div>
        <table class="smi-table">
          <tr v-for="it in downList" :key="it.name">
            <td>{{ it.name }}</td>
            <td :class="pctClass(it.changePct)">{{ fmtPct(it.changePct) }}</td>
          </tr>
          <tr v-if="!downList.length"><td class="empty-tip">暂无数据</td></tr>
        </table>
      </div>
    </div>
    <div class="empty-tip" v-if="module.method === 'TONGDAXIN_LEGACY'">数据口径：通达信 Legacy（历史导入）</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { SectorModule } from "../types/smi";
import { fmtPct, pctClass } from "../utils/format";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ module: SectorModule }>();
const tab = ref<"industry" | "concept">("industry");

const upList = computed(() => (tab.value === "industry" ? props.module.industryTop5 : props.module.conceptTop5));
const downList = computed(() => (tab.value === "industry" ? props.module.industryBottom5 : props.module.conceptBottom5));
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}
.tabs button {
  background: var(--panel-2);
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
}
.tabs button.active {
  color: var(--text);
  border-color: var(--blue);
}
.dual {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.mini-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
}
@media (max-width: 767px) {
  .dual {
    grid-template-columns: 1fr;
  }
}
</style>
