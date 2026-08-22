export type ModuleStatus =
  | "FINAL"
  | "PENDING"
  | "STALE"
  | "PARTIAL"
  | "UNAVAILABLE"
  | "ERROR";

export interface ModuleBase {
  status: ModuleStatus;
  dataDate: string | null;
  source?: string[];
  errors?: string[];
  warnings?: string[];
  reason?: string;
}

export interface IndexItem {
  code: string;
  name: string;
  close: number | null;
  previousClose: number | null;
  changePct: number | null;
  source?: string | null;
}

export interface MarketIndexModule extends ModuleBase {
  items: IndexItem[];
}

export interface TurnoverModule extends ModuleBase {
  unit: string;
  turnoverToday: number | null;
  turnoverPrevious: number | null;
  turnoverDelta: number | null;
  turnoverChangePct: number | null;
  volumeState: "EXPANSION" | "CONTRACTION" | "FLAT" | "UNKNOWN" | string;
}

export interface SentimentModule extends ModuleBase {
  riseCount: number | null;
  fallCount: number | null;
  flatCount: number | null;
  suspendedCount: number | null;
  nonStLimitUpCount: number | null;
  stLimitUpCount: number | null;
  nonStLimitDownCount: number | null;
  stLimitDownCount: number | null;
  brokenLimitCount: number | null;
  limitSealRatePct: number | null;
  maxLimitUpStreak: number | null;
}

export interface SectorEntry {
  code?: string;
  name: string;
  changePct: number | null;
  turnoverRate?: number | null;
  riseCount?: number | null;
  fallCount?: number | null;
  leader?: string;
}

export interface SectorModule extends ModuleBase {
  method: string;
  industryTop5: SectorEntry[];
  industryBottom5: SectorEntry[];
  conceptTop5: SectorEntry[];
  conceptBottom5: SectorEntry[];
}

export interface FlowEntry {
  code?: string;
  name: string;
  netInflowYi: number | null;
}

export interface FundFlowModule extends ModuleBase {
  method: string;
  unit: string;
  industryInflowTop10: FlowEntry[];
  industryOutflowTop10: FlowEntry[];
  conceptInflowTop10: FlowEntry[];
  conceptOutflowTop10: FlowEntry[];
  stockInflowTop10: FlowEntry[];
  stockOutflowTop10: FlowEntry[];
}

export interface NorthboundQuarterlyHoldingItem {
  code: string;
  hkexStockCode?: string;
  name: string;
  shareholding: string;
  pctOfIssued: string | null;
  market?: string;
}

export interface NorthboundModule extends ModuleBase {
  mode: string;
  sourceSystem?: string;
  officialDisclosureCompatible?: boolean;

  dailyTurnover?: {
    status: ModuleStatus;
    value: number | null;
    reason?: string;
  };

  activeSecurities?: {
    status: ModuleStatus;
    items: unknown[];
    reason?: string;
  };

  legacyNetFlow?: {
    status: ModuleStatus;
    reason?: string;
  };

  overlap?: {
    status: ModuleStatus;
    items: unknown[];
    reason?: string;
  };

  quarterlyHolding?: {
    status: ModuleStatus;
    asOf: string | null;
    publishedAt?: string | null;
    reason?: string;
    items: NorthboundQuarterlyHoldingItem[];
  };

  legacyImportedFields?: {
    status: ModuleStatus;
    totalNetInflow: number | null;
    shanghaiNetInflow: number | null;
    shenzhenNetInflow: number | null;
    netBuyTop10: FlowEntry[];
    netSellTop10: FlowEntry[];
    sameDirectionIn: string[];
    sameDirectionOut: string[];
    excludeFromOfficialTimeSeries: boolean;
    excludeFromTrackScoring: boolean;
  };
}

export interface QualityValue {
  value: number | null;
  quality?: string;
  unit?: string;
}

export interface MarginModule extends ModuleBase {
  unit: string;
  /** FINAL 必有；PENDING/STALE/ERROR 可缺省或 null（R10-P3-02） */
  financingBalance?: number | null;
  securitiesLendingBalance?: number | null;
  marginBalance?: number | null;
  marginBalanceChange?: number | null;
  financingBuyAmount?: number | null;
  financingNetBuyAmount?: QualityValue;
  securitiesLendingNetSellVolume?: QualityValue;
  legacySecuritiesLendingNetSellAmount?: QualityValue;
  marginTradeAmount?: QualityValue;
  marginTradeSharePct?: QualityValue;
  /** 非 FINAL 时展示最近已披露的官方两融余额；可能是 T-1，也可能因缺口回退到更早交易日，以 dataDate 为准（R10-P3-01） */
  latestPublishedReference?: {
    dataDate: string;
    financingBalance: number;
    securitiesLendingBalance: number;
    marginBalance: number;
  } | null;
}

export interface TrackItem {
  date: string;
  trackId: string;
  trackName: string;
  positioning: string;
  turnoverRank: number | null;
  turnoverUniverseSize?: number | null;
  turnoverPercentile?: number | null;
  mainNetInflow: number | null;
  mainNetInflowPercentile?: number | null;
  continuousInflowDays: number | null;
  maAlignment: unknown;
  rps60: number | null;
  excessReturn20d: number | null | string;
  limitUpCount: number | null;
  limitUpRate?: number | null;
  ladderCompleteness: unknown;
  redStockRatio: number | null | string;
  coreCatalyst: unknown;
  earningsRealization: unknown;
  score: number | null;
  coveragePct: number | null;
  decision: string;
  /** R12-PLAN-1：seed=种子赛道；dynamic:rank=N/…=当日动态候选 */
  selectionReason?: string;
  /** R12-PLAN-4：四级判定英文码（CORE_MAIN 等；历史快照缺失） */
  decisionCode?: string;
  /** R12-PLAN-4：四维度达标（capital/trend/emotion/logic；true/false/null=数据不足） */
  dimensionPass?: Record<string, boolean | null>;
  /** R13-P2-01/R15：数据就绪态。READY=正式评分成员；DEGRADED=降置信；
   *  WARMING_UP=冷启动预热（历史不足 minHistoryDays，不参与正式评分，
   *  score/decision 非成熟输出）；INSUFFICIENT/FETCH_FAILED=数据不足/获取失败 */
  dataReadiness?: "READY" | "DEGRADED" | "WARMING_UP" | "INSUFFICIENT" | "FETCH_FAILED" | string;
  /** R15：close 历史已累积交易日数（WARMING_UP 判定的依据） */
  historyDays?: number | null;
}

export interface TracksModule extends ModuleBase {
  configVersion: string;
  sourceSystem?: string;
  /** 模块级覆盖契约（R13-P2-02 三态；TRACKS_SUFFICIENT/INSUFFICIENT 为历史取值） */
  decision?: "TRACKS_SUFFICIENT" | "TRACKS_DEGRADED" | "TRACKS_INSUFFICIENT" | "INSUFFICIENT";
  /** R13-P2-02：模块级数据就绪态（READY/DEGRADED/FAILED） */
  dataReadiness?: "READY" | "DEGRADED" | "FAILED" | string;
  coveragePct?: number | null;
  /** R13-P2-02：coverage 目标线/硬地板（track-scoring.yaml 单一真源透传） */
  coverageTargetPct?: number | null;
  coverageHardFloorPct?: number | null;
  /** R13-P2-01：冷启动预热中板块（信息性，不参与正式评分） */
  warmingUpBoards?: string[];
  items: TrackItem[];
}

export interface SummaryModule extends ModuleBase {
  generator: string;
  indexAndTurnover: string;
  sentiment: string;
  fundFlow: string;
  margin: string;
  trackConclusion: string;
  marketEnvironment: string;
  northbound: string;
  riskWarning: string;
}

export interface DailySnapshot {
  schemaVersion: string;
  tradeDate: string;
  generatedAt: string | null;
  updatedAt: string | null;
  revision: number;
  overallStatus: string;
  generationReason: string | null;
  market: string;
  timezone: string;

  meta: {
    sourceSystem: string;
    legacy: boolean;
    importedFromExcel: boolean;
    officialDisclosureCompatibility: boolean;
  };

  modules: {
    marketIndex: MarketIndexModule;
    turnover: TurnoverModule;
    sentiment: SentimentModule;
    sectorPerformance: SectorModule;
    fundFlow: FundFlowModule;
    northbound: NorthboundModule;
    margin: MarginModule;
    tracks: TracksModule;
    summary: SummaryModule;
  };

  validation: {
    calendarExpectedTradingDay: boolean;
    marketDateVerified: boolean;
    requiredIndicesPresent: boolean;
    stockUniverseCheckPassed: boolean;
    criticalErrors: unknown[];
    warnings: unknown[];
  };
}

export interface Manifest {
  schemaVersion: string;
  /** 三指针（R7-P1）：最新已采集 / 最新 D0 收盘完整 / 最新 D+1 全 FINAL */
  latestCapturedDate: string;
  latestCloseCompleteDate: string | null;
  latestFinalDate: string | null;
  /** 已废弃别名，与 latestCapturedDate 同值 */
  latestDate?: string;
  updatedAt: string;
  availableDates: string[];
}
