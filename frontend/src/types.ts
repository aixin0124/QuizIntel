export type SurveyStatus = "draft" | "collecting" | "ended" | "archived";

export type SurveyQuestion = {
  question_id: string;
  text: string;
  question_type: string;
  options: string[];
  research_tag: string;
  required: boolean;
};

export type WrappedQuestion = {
  question_id: string;
  public_text: string;
  question_type: string;
  options: string[];
  research_tag: string;
  source_text: string;
  required: boolean;
  research_refs?: string[];
  rationale?: string;
};

export type WrappedSurvey = {
  survey_name: string;
  theme: string;
  tagline: string;
  intro: string;
  disclosure: string;
  result_types: Array<{ name: string; description: string }>;
  questions: WrappedQuestion[];
  brand_goal: string;
  source: string;
  dimensions?: Array<{ key: string; name: string; description: string; high_pole: string; low_pole: string }>;
  analysis_method?: string;
};

export type SurveySummary = {
  id: number;
  survey_name: string;
  theme: string;
  source: string;
  created_at: string;
  response_count: number;
  status: SurveyStatus;
  target_sample_count?: number | null;
  ended_at?: string | null;
  deleted_at?: string | null;
  share_token?: string | null;
  prompt_version?: string | null;
  model_name?: string | null;
  generation_latency_ms?: number | null;
  quality_score?: number | null;
  tenant_id?: number | null;
  team_id?: number | null;
  team_name?: string | null;
  moderation_status?: "pending" | "approved" | "rejected" | string;
};

export type DimensionBreakdown = {
  key: string;
  name: string;
  score: number;
  signal: string;
  description: string;
};

export type ResultAnalysis = {
  summary: string;
  personality_reference?: string;
  dimension_breakdown: DimensionBreakdown[];
  evidence: Array<{ question: string; answer: string; reason: string; rationale?: string }>;
  strengths: string[];
  watchouts: string[];
  advice: string;
};

export type ResultPayload = {
  name: string;
  description: string;
  strengths?: string[];
  watchouts?: string[];
  advice?: string;
  dimension_scores?: Record<string, number>;
  analysis?: ResultAnalysis;
};

export type PublicSurveyData = {
  id: number;
  share_token?: string | null;
  submitted?: boolean;
  survey?: WrappedSurvey;
};

export type DimensionStat = {
  key: string;
  name: string;
  description: string;
  high_pole?: string;
  low_pole?: string;
  score?: number | null;
  index?: number | null;
  positive_count?: number | null;
  neutral_count?: number | null;
  negative_count?: number | null;
  coverage_count: number;
  mapped_question_ids: string[];
  mapped_research_tags: string[];
  conclusion?: string;
};

export type QuestionStat = {
  question_id: string;
  question: string;
  research_tag: string;
  answered_count: number;
  answer_rate: number;
  options: Array<{ option: string; count: number; percentage: number }>;
  dimension_keys: string[];
};

export type CrossAnalysisRow = {
  question_id: string;
  question: string;
  research_tag: string;
  by_result_type: Record<string, Record<string, number>>;
};

export type CollectionTrend = {
  date: string;
  count: number;
  cumulative_count: number;
};

export type CompletionStat = {
  question_id: string;
  question: string;
  answered_count: number;
  answer_rate: number;
  dropout_rate: number;
};

export type AnalyticsSummary = {
  response_count: number;
  result_counts: Record<string, number>;
  option_counts: Record<string, Record<string, number>>;
  research_tags: string[];
  dimension_stats?: DimensionStat[];
  question_stats?: QuestionStat[];
  cross_analysis?: CrossAnalysisRow[];
  trend_stats?: CollectionTrend[];
  completion_stats?: CompletionStat[];
  sample_warning?: string;
  credibility_note?: string;
};

export type ResearchAnalysis = {
  generated_at: string;
  research_goal: string;
  theme: string;
  response_count: number;
  result_counts: Record<string, number>;
  research_tags: string[];
  dimensions: DimensionStat[];
  questions: QuestionStat[];
  key_findings: string[];
  research_conclusion: string;
  long_summary: string;
  limitations: string;
  analysis_method: string;
};

export type ResponseRow = {
  id: number;
  survey_version: number;
  result_type: string;
  created_at: string;
  submitted_at?: string | null;
  source: "public_link" | "admin_preview" | "test" | string;
  duration_seconds?: number | null;
  is_test: boolean;
  is_invalid: boolean;
  invalid_reason?: string | null;
  answers: Record<string, unknown>;
  research_answers: Record<string, unknown>;
  dimension_scores: Record<string, number>;
  analysis: Record<string, unknown>;
};

export type GenerationRecord = {
  id: number;
  survey_id?: number | null;
  prompt_version: string;
  model_name: string;
  latency_ms: number;
  token_estimate: number;
  cost_estimate: number;
  quality_score: number;
  retry_count: number;
  status: string;
  error_message?: string | null;
  created_at: string;
};

export type AnalyticsPayload = {
  status: SurveyStatus;
  target_sample_count?: number | null;
  ended_at?: string | null;
  summary: AnalyticsSummary;
  analysis: ResearchAnalysis | null;
  survey: WrappedSurvey;
  responses: ResponseRow[];
  generations: GenerationRecord[];
};

export type AdminUser = {
  id: number;
  username: string;
  role: "platform_admin" | "owner" | "tenant_owner" | "survey_admin" | "admin" | "viewer" | "member" | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  display_name?: string | null;
  tenant_id?: number | null;
};

export type Team = {
  id: number;
  tenant_id: number;
  name: string;
  description?: string | null;
  created_at: string;
  created_by?: number | null;
  member_role?: "manager" | "editor" | "viewer" | string;
  member_count?: number;
  survey_count?: number;
};

export type TeamMember = {
  id: number;
  username: string;
  display_name?: string | null;
  email?: string | null;
  is_active: boolean;
  member_role: "manager" | "editor" | "viewer" | string;
  status: string;
  created_at: string;
  responded_at?: string | null;
};

export type TeamInvitation = {
  id: number;
  team_id: number;
  team_name?: string;
  permission: "viewer" | "editor" | string;
  status: "pending" | "accepted" | "rejected" | string;
  created_at: string;
  responded_at?: string | null;
  invited_by_username?: string | null;
  invited_by_name?: string | null;
  invitee_username?: string | null;
  invitee_name?: string | null;
};

export type SurveyPermission = {
  survey_id: number;
  user_id: number;
  permission: "viewer" | "editor" | string;
  username: string;
  display_name?: string | null;
  email?: string | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
};

export type AccountProfile = {
  id: number;
  username: string;
  display_name?: string | null;
  role: string;
  tenant_id?: number | null;
  tenant_name?: string | null;
  workspace_name?: string | null;
  token_balance?: number | null;
  token_used?: number | null;
};

export type BillingOverview = {
  tenant_id: number | null;
  tenant_name: string;
  balance: number;
  used: number;
  today_used: number;
  api_calls: number;
  average_latency_ms: number;
  pending_requests: number;
  recent_usage: Array<{
    id: number;
    survey_id?: number | null;
    survey_name?: string | null;
    prompt_version: string;
    model_name: string;
    token_estimate: number;
    status: string;
    created_at: string;
  }>;
};

export type TokenRequest = {
  id: number;
  tenant_id: number;
  tenant_name?: string;
  requested_by: number;
  requested_by_name?: string;
  amount: number;
  reason: string;
  status: "pending" | "approved" | "rejected" | string;
  reviewed_at?: string | null;
  created_at: string;
};

export type PlatformOverview = {
  account_count: number;
  tenant_count?: number;
  user_count: number;
  survey_count: number;
  response_count: number;
  token_used: number;
  token_used_today: number;
  api_call_count: number;
  pending_token_requests: number;
  pending_reviews: number;
};

export type PlatformTenant = {
  id: number;
  name: string;
  slug: string;
  status: string;
  plan: string;
  token_balance: number;
  token_used: number;
  user_count: number;
  survey_count: number;
  created_at: string;
};

export type PlatformUser = {
  id: number;
  username: string;
  display_name?: string | null;
  email?: string | null;
  role: string;
  is_active: boolean;
  tenant_id?: number | null;
  tenant_name?: string | null;
  workspace_name?: string | null;
  token_used: number;
  survey_count: number;
  response_count: number;
  api_call_count: number;
  created_at: string;
  updated_at: string;
};

export type GenerationStep = {
  title: string;
  detail: string;
};

export type SurveyTemplate = {
  id: string;
  title: string;
  category: string;
  sourceUrl: string;
  summary: string;
  goal: string;
  themeHint: string;
};

export type ImportSurveyResponse = {
  title: string;
  source_url?: string;
  questions: SurveyQuestion[];
};
