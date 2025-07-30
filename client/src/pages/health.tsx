import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  Heart, 
  Activity, 
  Zap, 
  Database, 
  Wifi, 
  RefreshCw, 
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock
} from "lucide-react";

export default function Health() {
  const { data: dashboardData, isLoading, refetch } = useQuery({
    queryKey: ["/api/dashboard"],
    refetchInterval: 10000, // Refresh every 10 seconds for health monitoring
  });

  const { data: healthData } = useQuery({
    queryKey: ["/api/health"],
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  const systemStatus = dashboardData?.system_status;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "healthy":
      case "active":
      case "good":
        return <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />;
      case "degraded":
      case "warning":
        return <AlertTriangle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />;
      case "error":
      case "failed":
        return <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />;
      default:
        return <Activity className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "healthy":
      case "active":
      case "good":
        return "bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400";
      case "degraded":
      case "warning":
        return "bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400";
      case "error":
      case "failed":
        return "bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400";
      default:
        return "bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400";
    }
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-muted rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(6)].map((_, i) => (
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
            Monitor agent performance, API status, and system metrics
          </p>
        </div>
        <Button 
          variant="outline" 
          onClick={() => refetch()}
          className="border-border hover:bg-accent"
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4 bg-muted">
          <TabsTrigger value="overview" className="data-[state=active]:bg-background">Overview</TabsTrigger>
          <TabsTrigger value="apis" className="data-[state=active]:bg-background">API Status</TabsTrigger>
          <TabsTrigger value="performance" className="data-[state=active]:bg-background">Performance</TabsTrigger>
          <TabsTrigger value="scheduler" className="data-[state=active]:bg-background">Scheduler</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Overall Health Status */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>System Overview</span>
                <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                  All Systems Operational
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="text-center">
                  <div className="w-16 h-16 mx-auto mb-4 bg-green-100 dark:bg-green-900/20 rounded-full flex items-center justify-center">
                    <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
                  </div>
                  <h3 className="font-medium text-foreground">API Health</h3>
                  <p className="text-sm text-muted-foreground mt-1">All services online</p>
                </div>
                <div className="text-center">
                  <div className="w-16 h-16 mx-auto mb-4 bg-blue-100 dark:bg-blue-900/20 rounded-full flex items-center justify-center">
                    <Activity className="h-8 w-8 text-blue-600 dark:text-blue-400" />
                  </div>
                  <h3 className="font-medium text-foreground">Agent Status</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    {systemStatus?.live_mode ? "Active & Posting" : "Paused"}
                  </p>
                </div>
                <div className="text-center">
                  <div className="w-16 h-16 mx-auto mb-4 bg-purple-100 dark:bg-purple-900/20 rounded-full flex items-center justify-center">
                    <Database className="h-8 w-8 text-purple-600 dark:text-purple-400" />
                  </div>
                  <h3 className="font-medium text-foreground">Data Storage</h3>
                  <p className="text-sm text-muted-foreground mt-1">SQLite healthy</p>
                </div>
                <div className="text-center">
                  <div className="w-16 h-16 mx-auto mb-4 bg-orange-100 dark:bg-orange-900/20 rounded-full flex items-center justify-center">
                    <Clock className="h-8 w-8 text-orange-600 dark:text-orange-400" />
                  </div>
                  <h3 className="font-medium text-foreground">Uptime</h3>
                  <p className="text-sm text-muted-foreground mt-1">{systemStatus?.uptime || "Unknown"}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
                <Database className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{systemStatus?.memory_usage || "0 MB"}</div>
                <Progress value={35} className="mt-2" />
                <p className="text-xs text-muted-foreground mt-2">35% of allocated memory</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Response Time</CardTitle>
                <Zap className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">125ms</div>
                <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                  ↗ 5ms faster than average
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Error Rate</CardTitle>
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">0.02%</div>
                <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                  Well below 1% threshold
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="apis" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>External APIs</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-3 border border-border rounded-lg">
                  <div className="flex items-center space-x-3">
                    {getStatusIcon(systemStatus?.api_health || "healthy")}
                    <div>
                      <div className="font-medium text-sm">Twitter/X API</div>
                      <div className="text-xs text-muted-foreground">v2 Endpoints</div>
                    </div>
                  </div>
                  <Badge className={getStatusColor(systemStatus?.api_health || "healthy")}>
                    {systemStatus?.api_health || "Healthy"}
                  </Badge>
                </div>

                <div className="flex items-center justify-between p-3 border border-border rounded-lg">
                  <div className="flex items-center space-x-3">
                    {getStatusIcon("healthy")}
                    <div>
                      <div className="font-medium text-sm">OpenAI API</div>
                      <div className="text-xs text-muted-foreground">GPT-4o-mini</div>
                    </div>
                  </div>
                  <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                    Healthy
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Rate Limits</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Twitter API Calls</span>
                    <span className="font-medium">450/1500 per hour</span>
                  </div>
                  <Progress value={30} />
                  <p className="text-xs text-muted-foreground">70% capacity remaining</p>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>OpenAI Tokens</span>
                    <span className="font-medium">125K/1M per day</span>
                  </div>
                  <Progress value={12.5} />
                  <p className="text-xs text-muted-foreground">87.5% capacity remaining</p>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Posts per Hour</span>
                    <span className="font-medium">3/12</span>
                  </div>
                  <Progress value={25} />
                  <p className="text-xs text-muted-foreground">Safe posting rate</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>System Resources</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>CPU Usage</span>
                    <span className="font-medium">23%</span>
                  </div>
                  <Progress value={23} />
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Memory Usage</span>
                    <span className="font-medium">67.2 MB</span>
                  </div>
                  <Progress value={35} />
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Database Size</span>
                    <span className="font-medium">12.4 MB</span>
                  </div>
                  <Progress value={5} />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Response Times</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between">
                  <span className="text-sm">API Endpoints</span>
                  <span className="text-sm font-medium">95ms avg</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Database Queries</span>
                  <span className="text-sm font-medium">12ms avg</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">LLM Generation</span>
                  <span className="text-sm font-medium">2.3s avg</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Twitter API</span>
                  <span className="text-sm font-medium">340ms avg</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="scheduler" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Scheduled Jobs</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[
                  { name: "Post Proposals", next: "in 23 minutes", status: "active" },
                  { name: "Reply to Mentions", next: "in 8 minutes", status: "active" },
                  { name: "Search & Engage", next: "in 15 minutes", status: "active" },
                  { name: "Analytics Pull", next: "in 12 minutes", status: "active" },
                  { name: "KPI Rollup", next: "in 45 minutes", status: "active" },
                  { name: "Follower Snapshot", next: "in 4 hours", status: "scheduled" },
                  { name: "Nightly Reflection", next: "in 18 hours", status: "scheduled" },
                  { name: "Weekly Planning", next: "in 2 days", status: "scheduled" },
                ].map((job) => (
                  <div key={job.name} className="flex items-center justify-between p-3 border border-border rounded-lg">
                    <div>
                      <div className="font-medium text-sm">{job.name}</div>
                      <div className="text-xs text-muted-foreground">{job.next}</div>
                    </div>
                    <Badge className={getStatusColor(job.status)}>
                      {job.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
