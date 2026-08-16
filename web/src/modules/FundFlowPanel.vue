<template>
  <div class="card">
    <h3>
      主力资金流向
      <StatusBadge :status="module.status" />
    </h3>
    <div class="tabs">
      <button :class="{ active: tab === 'industry' }" @click="tab = 'industry'">行业</button>
      <button :class="{ active: tab === 'concept' }" @click="tab = 'concept'">概念</button>
      <button :class="{ active: tab === 'stock' }" @click="tab = 'stock'">个股</button>
    </div>
    <div class="dual">
      <div>
        <div class="mini-title up">净流入 TOP10</div>
        <table class="smi-table">
          <tr v-for="it in inList" :key="it.name">
            <td>{{ it.name }}</td>
            <td class="up">{{ fmt(it.netInflowYi) }}</td>
          </tr>
          <tr v-if="!inList.length"><td class="empty-tip">{{ emptyTip }}</td></tr>
        </table>
      </div>
      <div>
        <div class="mini-title down">净流出 TOP10</div>
        <table class="smi-table">
          <tr v-for="it in outList" :key="it.name">
            <td>{{ it.name }}</td>
            <td class="down">{{ fmt(it.netInflowYi) }}</td>
          </tr>
          <tr v-if="!outList.length"><td class="empty-tip">{{ emptyTip }}</td></tr>
        </table>
      </div>
    </div>
    <!-- 口径页脚：展示单位与口径；含 EASTMONEY_PUSH2HIS_HISTORICAL（东方财富历史数据回补，免费源）标注（标准 fundFlow 口径页脚） -->
    <div class="empty-tip">单位：${module.unit || "亿元"} · 数据口径：{{ methodLabel }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { FundFlowModule } from "../types/smi";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ module: FundFlowModule }>();
const tab = ref<"industry" | "concept" | "stock">("industry");

const inList = computed(() => {
  const m = props.module;
  if (tab.value === "industry") return m.industryInflowTop10;
  if (tab.value === "concept") return m.conceptInflowTop10;
  return m.stockInflowTop10;
});

const outList = computed(() => {
  const m = props.module;
  if (tab.value === "industry") return m.industryOutflowTop10;
  if (tab.value === "concept") return m.conceptOutflowTop10;
  return m.stockOutflowTop10;
});

function fmt(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}亿`;
}

// 空列表提示：个股榜空时明确提示“历史免费源不可用”，行业/概念沿用通用提示（任务约定）
const emptyTip = computed(() => (tab.value === "stock" ? "暂无数据（历史免费源不可用）" : "暂无数据"));

// 口径页脚文案：东方财富主口径 / 东方财富历史回补（免费源）/ 通达信系
const methodLabel = computed(() => {
  const m = props.module.method;
  if (m === "EASTMONEY_MAIN_FORCE") return "东方财富";
  if (m === "EASTMONEY_PUSH2HIS_HISTORICAL") return "东方财富（历史免费源回补，仅供参考）";
  if (m === "THS_MAIN_FORCE") return "通达信";
  return "通达信 Legacy";
});
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
