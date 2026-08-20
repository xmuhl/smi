import type {
  DailySnapshot,
  Manifest,
  ModuleStatus,
} from "../types/smi";

export const STATUS_TEXT: Record<
  ModuleStatus,
  {
    text: string;
    cls: string;
    icon: string;
  }
> = {
  FINAL: {
    text: "已更新",
    cls: "ok",
    icon: "✓",
  },
  PENDING: {
    text: "待披露",
    cls: "info",
    icon: "◷",
  },
  STALE: {
    text: "数据延迟",
    cls: "warn",
    icon: "!",
  },
  PARTIAL: {
    text: "部分数据",
    cls: "info",
    icon: "◐",
  },
  UNAVAILABLE: {
    text: "不可用",
    cls: "neutral",
    icon: "—",
  },
  ERROR: {
    text: "获取失败",
    cls: "error",
    icon: "×",
  },
};

export function fmtPct(
  value: number | null | undefined,
  digits = 2,
): string {
  if (
    value === null
    || value === undefined
    || Number.isNaN(value)
  ) {
    return "—";
  }

  const sign = value > 0 ? "+" : "";

  return `${sign}${value.toFixed(digits)}%`;
}

export function fmtNum(
  value: number | null | undefined,
  digits = 2,
): string {
  if (
    value === null
    || value === undefined
    || Number.isNaN(value)
  ) {
    return "—";
  }

  return value.toFixed(digits);
}

export function fmtYi(
  value: number | null | undefined,
): string {
  if (
    value === null
    || value === undefined
    || Number.isNaN(value)
  ) {
    return "—";
  }

  const sign = value > 0 ? "+" : "";

  return `${sign}${value.toFixed(2)}亿`;
}

export function pctClass(
  value: number | null | undefined,
): string {
  if (
    value === null
    || value === undefined
    || Number.isNaN(value)
  ) {
    return "flat";
  }

  if (value > 0) return "up";
  if (value < 0) return "down";

  return "flat";
}

export function loadManifest(): Promise<Manifest> {
  return fetch(
    `/data/manifest.json?t=${Date.now()}`,
    {
      cache: "no-store",
    },
  ).then((response) => {
    if (!response.ok) {
      throw new Error(
        `manifest ${response.status}`,
      );
    }

    return response.json();
  });
}

export function loadDaily(
  date: string,
): Promise<DailySnapshot> {
  const year = date.slice(0, 4);

  return fetch(
    `/data/daily/${year}/${date}.json?t=${Date.now()}`,
    {
      cache: "no-store",
    },
  ).then((response) => {
    if (!response.ok) {
      throw new Error(
        `daily ${date} ${response.status}`,
      );
    }

    return response.json();
  });
}

export function volumeStateText(
  state: string | undefined,
): string {
  if (state === "EXPANSION") return "放量";
  if (state === "CONTRACTION") return "缩量";
  if (state === "FLAT") return "平量";

  return "待比较";
}

export function decisionText(
  decision: string,
): string {
  // R12-PLAN-4 四级判定（新枚举优先；PASS/WATCH/AVOID 兼容历史快照）
  if (decision === "CORE_MAIN") return "核心主赛道";
  if (decision === "SECONDARY_MAIN") return "次主线/轮动主线";
  if (decision === "SHORT_LINE") return "短线支线";
  if (decision === "PULSE_AVOID") return "一日游脉冲/回避";

  if (decision === "PASS") return "达标";
  if (decision === "WATCH") return "观察";
  if (decision === "AVOID") return "规避";

  if (decision === "INSUFFICIENT") {
    return "数据不足";
  }

  return decision;
}

export function decisionClass(
  decision: string,
): string {
  // 快照 items 的 decision 为中文标签（历史为 PASS 系英文码），两种都匹配
  if (
    decision === "CORE_MAIN" ||
    decision === "核心主赛道" ||
    decision === "PASS" ||
    decision === "达标"
  ) {
    return "up";
  }
  if (
    decision === "PULSE_AVOID" ||
    decision === "一日游脉冲/回避" ||
    decision === "AVOID" ||
    decision === "规避"
  ) {
    return "down";
  }

  return "flat";
}
