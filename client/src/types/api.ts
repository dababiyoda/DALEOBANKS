// Response shapes for the FastAPI backend.
// Sources of truth: app.py (/api/dashboard, /api/health) and
// services/analytics.py get_analytics_summary (/api/analytics).

export interface SystemStatus {
  api_health: string;
  rate_limits: string;
  ethics_guard: string;
  memory_usage: string;
  uptime: string;
  live_mode: boolean;
  crisis_state: string;
  crisis_reason?: string | null;
}

export interface ActivityItem {
  id: string;
  kind: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export interface PersonaPreview {
  handle?: string;
  mission?: string;
  beliefs?: string[];
  doctrine?: string[];
  content_mix?: Record<string, number>;
  [key: string]: unknown;
}

export interface DashboardResponse {
  kpis: Record<string, number>;
  recent_activity: ActivityItem[];
  system_status: SystemStatus;
  persona_preview: PersonaPreview;
  goal_mode: string;
}

export interface AnalyticsSummary {
  fame_score: number;
  fame_score_change: number;
  impact_score: number;
  impact_change: number;
  revenue_today: number;
  revenue_change: number;
  authority_signals: number;
  penalty_score: number;
  objective_score: number;
  follower_count: number;
  follower_change: number;
  tweets_today: number;
  engagement_rate: number;
  last_updated: string;
}

export interface HealthResponse {
  ok: boolean;
  timestamp: string;
}
