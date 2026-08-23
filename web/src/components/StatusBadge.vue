<template>
  <!-- UI 评审 A3（产品裁决 2026-08-23）：FINAL 为常态，徽标仅在非 FINAL 状态渲染，消除每卡重复噪音 -->
  <span v-if="props.status !== 'FINAL'" class="badge" :class="meta.cls">{{ meta.icon }} {{ meta.text }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ModuleStatus } from "../types/smi";
import { STATUS_TEXT } from "../utils/format";

const props = defineProps<{ status?: ModuleStatus }>();

const meta = computed(() => STATUS_TEXT[props.status ?? "PENDING"] ?? STATUS_TEXT.PENDING);
</script>
