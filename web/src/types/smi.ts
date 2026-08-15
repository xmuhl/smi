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
  financingBalance: number | null;
  securitiesLendingBalance: number | null;
  marginBalance: number | null;
  marginBalanceChange: number | null;
  financingBuyAmount: number | null;
  financingNetBuyAmount: QualityValue;
  securitiesLendingNetSellVolume: QualityValue;
  legacySecuritiesLendingNetSellAmount?: QualityValue;
  marginTradeAmount: QualityValue;
  marginTradeSharePct: QualityValue;
}

export interface TrackItem {
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
}

export interface TracksModule extends ModuleBase {
  configVersion: string;
  sourceSystem?: string;
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
  latestDate: string;
  latestFinalDate: string | null;
  updatedAt: string;
  availableDates: string[];
}
