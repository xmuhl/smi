<template>
  <div class="card">
    <h3>
      北向资金
      <StatusBadge :status="module.status" />
    </h3>

    <div v-if="module.mode === 'POST_20240819_LEGACY_IMPORTED'" class="notice">
      <b>历史口径已变更</b>：本页北向字段来自原 Excel（Legacy 导入），仅用于还原历史报表；2024-08-19 后官方披露口径已调整，Legacy 值不作为 SMI 官方北向连续序列。
    </div>
    <div v-else-if="module.mode === 'POST_20240819_QUARTERLY_ONLY'" class="notice">
      2024-08-19 起北向日度净买入/净流入不再按旧口径披露；V1 仅展示 HKEX 最近一期季度持仓。
    </div>
    <div v-else-if="module.mode === 'POST_20240819_OFFICIAL_REPLACEMENT'" class="notice">
      官方日度净流入自 2024-08-19 起停止披露，以下为截至 {{ module.quarterlyHolding?.asOf ?? "—" }} 的官方季度持仓（point-in-time，发布于 {{ module.quarterlyHolding?.publishedAt ?? "—" }}）。
    </div>

    <template v-if="legacy">
      <div class="grid grid-3">
        <div class="metric">
          <div class="label">北向合计净流入</div>
          <div class="value" :class="signClass(legacy.totalNetInflow)">{{ fmtYi(legacy.totalNetInflow) }}</div>
        </div>
        <div class="metric">
          <div class="label">沪股通</div>
          <div class="value" :class="signClass(legacy.shanghaiNetInflow)">{{ fmtYi(legacy.shanghaiNetInflow) }}</div>
        </div>
        <div class="metric">
          <div class="label">深股通</div>
          <div class="value" :class="signClass(legacy.shenzhenNetInflow)">{{ fmtYi(legacy.shenzhenNetInflow) }}</div>
        </div>
      </div>
      <div class="dual">
        <div>
          <div class="mini-title up">净买入 TOP10</div>
          <table class="smi-table">
            <tr v-for="it in legacy.netBuyTop10" :key="it.name">
              <td>{{ it.name }}</td>
              <td class="up">{{ fmtYi(it.netInflowYi) }}</td>
            </tr>
          </table>
        </div>
        <div>
          <div class="mini-title down">净卖出 TOP10</div>
          <table class="smi-table">
            <tr v-for="it in legacy.netSellTop10" :key="it.name">
              <td>{{ it.name }}</td>
              <td class="down">{{ fmtYi(it.netInflowYi) }}</td>
            </tr>
          </table>
        </div>
      </div>
      <div v-if="legacy.sameDirectionIn.length || legacy.sameDirectionOut.length" class="empty-tip">
        主力×北向同步流入：{{ legacy.sameDirectionIn.join("、") || "—" }}；同步流出：{{ legacy.sameDirectionOut.join("、") || "—" }}
      </div>
    </template>

    <template v-else-if="module.quarterlyHolding">
      <!-- UI 评审 A2/B1（产品裁决 2026-08-23）：低频 point-in-time 参考数据默认折叠为摘要行，可展开完整表 -->
      <div class="nb-summary-line" v-if="module.quarterlyHolding.asOf">
        <span>最近一期季度持仓（{{ module.quarterlyHolding.asOf }}）· {{ module.quarterlyHolding.items.length }} 只 · point-in-time 参考数据</span>
        <button class="link-btn" @click="toggleExpanded">{{ expanded ? "收起持仓表" : "展开持仓表（前 20 条）" }}</button>
      </div>
      <template v-if="expanded && module.quarterlyHolding.items.length">
      <table class="smi-table nb-table" v-if="module.quarterlyHolding.items.length">
        <tr>
          <th>代码</th>
          <th>名称</th>
          <th>持股数量</th>
          <th>占已发行股份</th>
          <th>市场</th>
        </tr>
        <tr
          v-for="it in module.quarterlyHolding.items.slice(0, 20)"
          :key="it.code"
        >
          <td>{{ it.code }}</td>
          <td>{{ it.name }}</td>
          <td>{{ it.shareholding ?? "—" }}</td>
          <td>
            {{ it.pctOfIssued != null ? it.pctOfIssued + "%" : "—" }}
          </td>
          <td>{{ marketText(it.market) }}</td>
        </tr>
      </table>
      <div
        v-if="module.quarterlyHolding.items.length > 20"
        class="empty-tip"
      >
        共 {{ module.quarterlyHolding.items.length }} 条，仅展示前 20 条
      </div>
      </template>
      <div v-if="!module.quarterlyHolding.items.length" class="empty-tip">季度持仓暂未取得（{{ module.quarterlyHolding.status }}）</div>
    </template>

    <div class="empty-tip" v-if="!legacy">
      日度成交额 / 活跃证券：{{ module.dailyTurnover?.status === "UNAVAILABLE" ? "SMI V1 暂未提供稳定自动采集" : "未取得" }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { NorthboundModule } from "../types/smi";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ module: NorthboundModule }>();

const legacy = computed(() => props.module.legacyImportedFields ?? null);

// UI 评审 A2：折叠状态跨会话记忆
const expanded = ref(localStorage.getItem("smi-nb-expanded") === "1");
function toggleExpanded() {
  expanded.value = !expanded.value;
  localStorage.setItem("smi-nb-expanded", expanded.value ? "1" : "0");
}

function marketText(market: string | null | undefined): string {
  if (market === "sh") return "沪股通";
  if (market === "sz") return "深股通";
  if (market === null || market === undefined || market === "") return "—";
  return market;
}

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
</script>

<style scoped>
.notice {
  background: rgba(255, 202, 40, 0.08);
  border: 1px solid rgba(255, 202, 40, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--yellow);
  margin-bottom: 10px;
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
