<template>
  <span class="badge" :class="meta.cls">{{ meta.icon }} {{ meta.text }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ModuleStatus } from "../types/smi";
import { STATUS_TEXT } from "../utils/format";

const props = defineProps<{ status?: ModuleStatus }>();

const meta = computed(() => STATUS_TEXT[props.status ?? "PENDING"] ?? STATUS_TEXT.PENDING);
</script>
