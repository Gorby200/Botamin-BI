// JSON contract — mirrors the pipeline output (pipeline/build.py).
// One shape for every metric, so the UI renders value + band colour + verdict +
// annotation uniformly (see components/Stat.tsx).

export type Band = "good" | "ok" | "bad" | "neutral";
export type Fmt = "pct" | "ratio" | "int" | "sec" | "float";

export interface Metric {
  id: string;
  name: string;
  value: number;
  thr_key: string | null;     // which threshold drives banding (for live re-band)
  comments: Partial<Record<Band, string>>; // full band→comment map
  fmt: Fmt;
  band: Band;
  verdict: string;            // "Хорошо" | "Приемлемо" | "Требует внимания" | ""
  comment: string;            // dynamic, band-dependent explanation
  desc: string;               // what the metric is
  why: string;                // why it matters to the analyst
  thresholds: { good: number; ok: number; direction: "higher" | "lower" } | null;
  numerator: number | null;
  denominator: number | null;
}

export interface ThresholdDef {
  key: string;
  label: string;
  fmt: Fmt;
  group: string;
  good: number;
  ok: number;
  direction: "higher" | "lower";
}

export interface LLMStatus {
  configured: boolean;
  provider: string;
  scope: string;              // focus | full | sample | off
  mode: "llm_single_pass" | "deterministic" | "llm" | "llm_tiered";
  calls_analyzed: number;
  calls_selected: number;
  available: boolean;
  note: string;
  tier1_analyzed?: number;
  tier2_analyzed?: number;
  tier3_run?: boolean;
  tier3_results?: ResearchData | null;
}

export interface DashboardMeta {
  source: string;
  generated_at: string;
  total_rows: number;
  period_from: string | null;
  period_to: string | null;
  llm: LLMStatus;
  data_quality: string[];
}

export interface FunnelStage {
  stage: string;              // S0..S4
  label: string;
  count: number;
  conversion_from_prev: number;
  share_of_engaged: number;
  dropped_abs: number;
  drop_attribution: {
    client_hangup?: number;
    bot_hangup?: number;
    technical?: number;
    context_loss?: number;
    controllable_loss?: number;
  };
}

export interface Driver extends Metric {
  prompt_block: string;
  volume_in: number;
  volume_out: number;
  mde_pp: number;
  sample_needed: number;
}

export interface NSM extends Metric {
  variants: Record<string, { label: string; value: number; hint: string }>;
  counts: {
    engaged: number; consent: number; meeting: number;
    qualified: number; qualified_net: number; disqualified: number;
  };
}

export interface PatternAudit {
  psy_id: string;
  name: string;
  polarity: "positive" | "negative";
  impact: string;
  prompt_block: string;
  category?: string;
  weight: number;
  share: number;
  count: number;
  lift_on_advance: number;
}

export interface ObjectionCluster {
  type: string;
  label: string;
  gap: string;
  count: number;
  verbatims: string[];
  by_stage: Record<string, number>;
}

export interface InstrumentationItem {
  id: string;
  name: string;
  needs: string;
  why: string;
  unlocks: string;
}

export interface LossAttribution {
  context: number;
  controllable: number;
  context_share: number;
  controllable_share: number;
  by_reason: { reason: string; label: string; count: number }[];
}

// ── V4 quality (bot-adapted): LLM judges layers, Python computes total/grade/outcome/gap ──
export interface QualityScore {
  macro: number; micro: number; overlap: number;
  total: number; grade: string; grade_name: string;
  breakdown: { macro_contribution: number; micro_contribution: number; overlap_contribution: number };
  outcome: number;
  gap: { gap: number; efficiency_ratio: number; interpretation: string };
}

export interface GapAnalysis {
  n: number;
  avg_quality: number;
  avg_outcome: number;
  avg_gap: number;
  grade_distribution: { grade: string; count: number }[];
  buckets: { closing_bottleneck: number; warm_base: number; aligned: number };
  interpretation: string;
}

export interface ProductIntelInsight {
  category: string; insight: string; quote: string; recommendation: string;
}
export interface ProductIntel {
  insights: ProductIntelInsight[];
  jtbd: { functional: string; emotional: string; trigger: string };
}

export interface Dashboard {
  meta: DashboardMeta;
  reach: { dials: number; engaged: number; metrics: Metric[] };
  nsm: NSM;
  funnel: FunnelStage[];
  drivers: Driver[];
  quality: { metrics: Metric[] };
  guardrails: Metric[];
  loss_attribution: LossAttribution;
  bottleneck: {
    driver_id: string; label: string; stage_from: string; stage_to: string;
    conversion: number; dropped_abs: number; prompt_block: string; rationale: string;
  };
  gap_analysis?: GapAnalysis | null;
  outcomes: { outcome: string; key: string; count: number; score: number }[];
  time_heatmap: { dow: number; hour: number; calls: number; advanced: number }[];
  duration_distribution: { bucket_sec: string; count: number }[];
  thresholds_defaults: ThresholdDef[];
  diagnostics: {
    pattern_audit: PatternAudit[];
    objection_clusters: ObjectionCluster[];
    pitch: {
      resonated: { phrase: string; stayed: number; left: number }[];
      fell_flat: { phrase: string; left: number; stayed: number }[];
    };
  };
  instrumentation_spec: InstrumentationItem[];
}

export interface BacklogItem {
  hypothesis: string;
  alternatives: string[];
  prompt_block: string;
  stage: string;
  evidence: { metric: string; value: number; patterns: string[]; verbatims: string[]; note: string };
  expected_driver_delta_pp: number;
  downstream_pass_through: number;
  expected_nsm_delta_pp: number;
  effort: "low" | "med" | "high";
  risk_guardrails: string[];
  confidence: number;
  ab_design: { variant: string; primary: string; mde_pp: number; sample: number; duration_days: number };
  priority: number;
}

export interface CustDevQuote { call_id: string; quote: string }
export interface CustDevCategory {
  key: string; label: string; count: number; recommendation: string; quotes: CustDevQuote[];
}
export interface CustDev {
  prompt: string;
  mode: string;
  total_conversations: number;
  categories: CustDevCategory[];
  summary: { theme: string; count: number; recommendation: string }[];
  note: string;
}

export interface CallIndex {
  id: string;
  page?: string;              // page file reference (e.g., "page_000")
  idx_in_page?: number;        // index within the page (0-49)
  datetime: string;
  duration_sec: number;
  status: string;
  end_attribution: string;
  furthest_stage: number;
  outcome: string;
  loss_layer: string;
  asr_severity: string;
  responsiveness: number;
  source: string;
  snippet: string;
}

export interface CallDetail {
  id: string;
  datetime: string;
  duration_sec: number;
  status: string;
  end_reason: string;
  audio_url: string;
  furthest_stage: number;
  outcome: string;
  summary: string;
  source: string;
  loss_layer: string;
  loss_reason: string;
  disqualified: boolean;
  stage_evidence: Record<string, { reached: boolean; quote: string }>;
  voice: {
    asr_breakdown: boolean; asr_severity: string; responsiveness: number;
    repair_attempts: number; bot_talk_share: number; longest_bot_monologue_words: number;
  };
  detected_patterns: { id: string; polarity: string; quote: string; name?: string }[];
  objections: { type: string; quote: string; root_cause?: string }[];
  quality?: QualityScore;
  product_intel?: ProductIntel;
  recommendations?: string[];
  transcript: { role: "bot" | "client" | "unknown"; text: string }[];
}

// ── Tier 3 Research Types ─────────────────────────────────────────────────

export interface TemporalPattern {
  time_window: string;
  characteristics: string;
  metrics: { connect_rate: number; meeting_rate: number; quality_score: number };
  difference_from_avg: string;
  hypothesis: string;
  recommendation: string;
}

export interface TemporalWarning {
  time_window: string;
  issue: string;
  possible_cause: string;
}

export interface TemporalAnalysis {
  patterns: TemporalPattern[];
  warnings: TemporalWarning[];
  overall_insights: string;
}

export interface FailureCluster {
  name: string;
  size_estimate: number;
  pct_of_failed: number;
  characteristics: string;
  typical_quotes: string[];
  stage_where_lost: string;
  hypothesis: string;
  prompt_fix_suggestion: string;
}

export interface FailureClustering {
  clusters: FailureCluster[];
  priority_order: string[];
  quick_wins: string[];
}

export interface ConversionSignal {
  signal: string;
  correlation: "strong" | "moderate" | "weak" | "negative";
  lift: string;
  explanation: string;
}

export interface ConversionSignals {
  strong_signals: ConversionSignal[];
  negative_predictors: ConversionSignal[];
  surprising_findings: string;
  scoring_model?: { weights: Record<string, number>; threshold: number };
}

export interface CustDevInsight {
  category: string;
  theme: string;
  quotes: string[];
  frequency: string;
  recommendation: string;
}

export interface CustDevHypothesis {
  hypothesis: string;
  validation_method: string;
}

export interface CustDevResearch {
  insights: CustDevInsight[];
  new_hypotheses: CustDevHypothesis[];
}

export interface ResearchData {
  generated_at: string;
  total_calls_analyzed: number;
  temporal: TemporalAnalysis | null;
  failure_clusters: FailureClustering | null;
  conversion_signals: ConversionSignals | null;
  custdev: CustDevResearch | null;
}
