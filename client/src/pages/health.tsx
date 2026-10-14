import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Heart,
  Activity,
  Database,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  HelpCircle,
} from "lucide-react";
import type { DashboardResponse } from "@/types/api";
import { deriveOverallHealth, OVERALL_HEALTH_LABEL, type OverallHealth } from "@/lib/health-status";

// Every value on this page comes from /api/dashboard's system_status, which
// the backend derives from observations taken at request time. Anything we
// do not measure is labelled "not instrumented" rather than given a number.

const NOT_INSTRUMENTED = "Not instrumented";

function statusTone(status: string | null | undefined): "good" | "warn" | "bad" | "unknown" {
  switch ((status ?? "").toLowerCase()) {
    case "healthy":
    case "good":
    case "active":
    case "operational":
    case "normal":
      return "good";
    case "degraded":
    case "warning":
    case "paused":
    case "stale":
      return "warn";
    case "unavailable":
    case "error":
    case "failed":
      return "bad";
    default:
      return "unknown";
  }
}

const TONE_CLASS = {
  good: "bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400",
  warn: "bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400",
  bad: "bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400",
  unknown: "bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400",
} as const;

function StatusIcon({ status }: { status: string | null | undefined }) {
  const tone = statusTone(status);
  if (tone === "good") return <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />;
  if (tone === "warn") return <AlertTriangle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />;
  if (tone === "bad") return <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />;
  return <HelpCircle className="h-4 w-4 text-muted-foreground" />;
}

function StatusRow({ label, detail, status }: { label: string; detail: string; status: string | null | undefined }) {
  const shown = status ?? "unknown";
  return (
    <div className="flex items-center justify-between p-3 border border-border rounded-lg">
      <div className="flex items-center space-x-3">
        <StatusIcon status={shown} />
        <div>
          <div className="font-medium text-sm">{label}</div>
          <div className="text-xs text-muted-foreground">{detail}</div>
        </div>
      </div>
      <Badge className={TONE_CLASS[statusTone(shown)]}>{shown}</Badge>
    </div>
  );
}

const OVERALL_TONE: Record<OverallHealth, keyof typeof TONE_CLASS> = {
  operational: "good",
  degraded: "warn",
  stale: "warn",
  unavailable: "bad",
  unknown: "unknown",
};

export default function Health() {
  const { data: dashboardData, isLoading, isError, refetch } = useQuery<DashboardResponse>({
    queryKey: ["/api/dashboard"],
    refetchInterval: 10000,
  });

  const systemStatus = isError ? undefined : dashboardData?.system_status;
  const overall = deriveOverallHealth(systemStatus, Date.now());
  const jobs = systemStatus?.scheduler?.jobs ?? [];

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-muted rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-32 bg-muted rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center">
            <Heart className="mr-3 h-8 w-8 text-red-500" />
            System Health
          </h1>
          <p className="text-muted-foreground mt-1">
            Observed status only. Unmeasured signals are shown as unknown, never as healthy.
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} className="border-border hover:bg-accent">
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 bg-muted">
          <TabsTrigger value="overview" className="data-[state=active]:bg-background">Overview</TabsTrigger>
          <TabsTrigger value="apis" className="data-[state=active]:bg-background">Dependencies</TabsTrigger>
          <TabsTrigger value="scheduler" className="data-[state=active]:bg-background">Scheduler</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>System Overview</span>
                <Badge className={TONE_CLASS[OVERALL_TONE[overall]]}>{OVERALL_HEALTH_LABEL[overall]}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="text-center">
                  <Activity className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <h3 className="font-medium text-foreground">Agent Status</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    {systemStatus ? (systemStatus.live_mode ? "Live mode armed" : "Not live") : "unknown"}
                  </p>
                </div>
                <div className="text-center">
                  <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <h3 className="font-medium text-foreground">Crisis State</h3>
                  <p className="text-sm text-muted-foreground mt-1">{systemStatus?.crisis_state ?? "unknown"}</p>
                </div>
                <div className="text-center">
                  <Database className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <h3 className="font-medium text-foreground">Memory</h3>
                  <p className="text-sm text-muted-foreground mt-1">{systemStatus?.memory_usage ?? "unknown"}</p>
                </div>
                <div className="text-center">
                  <Clock className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <h3 className="font-medium text-foreground">Uptime</h3>
                  <p className="text-sm text-muted-foreground mt-1">{systemStatus?.uptime ?? "unknown"}</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-6">
                Observed at: {systemStatus?.observed_at ?? "no observation"}. Response times, error rates and
                CPU usage: {NOT_INSTRUMENTED.toLowerCase()}.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="apis" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Dependencies</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <StatusRow label="X API client" detail="Authenticated v2 client" status={systemStatus?.api_health} />
              <StatusRow label="X rate limits" detail="Circuit breakers on X endpoints" status={systemStatus?.rate_limits} />
              <StatusRow label="Ragebait / ethics guard" detail="Generation-time guard flag" status={systemStatus?.ethics_guard} />
              <StatusRow label="LLM provider" detail="Health probe" status={NOT_INSTRUMENTED} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="scheduler" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Scheduled Jobs</span>
                <Badge
                  className={TONE_CLASS[systemStatus?.scheduler?.running === true ? "good" : systemStatus?.scheduler?.running === false ? "bad" : "unknown"]}
                >
                  {systemStatus?.scheduler?.running === true ? "running" : systemStatus?.scheduler?.running === false ? "stopped" : "unknown"}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {jobs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No scheduler jobs reported.</p>
              ) : (
                <div className="space-y-4">
                  {jobs.map((job) => (
                    <div key={job.id} className="flex items-center justify-between p-3 border border-border rounded-lg">
                      <div className="font-medium text-sm">{job.id}</div>
                      <div className="text-xs text-muted-foreground">{job.next_run ?? "not scheduled"}</div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
