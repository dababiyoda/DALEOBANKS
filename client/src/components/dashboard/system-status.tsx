import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";

interface SystemStatus {
  api_health?: string;
  rate_limits?: string;
  ethics_guard?: string;
  memory_usage?: string;
  uptime?: string;
  live_mode?: boolean;
}

interface SystemStatusProps {
  data?: SystemStatus;
}

export default function SystemStatus({ data }: SystemStatusProps) {
  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case "healthy":
      case "good":
      case "active":
        return <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">Healthy</Badge>;
      case "degraded":
      case "warning":
        return <Badge className="bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400">Warning</Badge>;
      case "error":
      case "failed": 
        return <Badge variant="destructive">Error</Badge>;
      default:
        return <Badge className="bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400">Unknown</Badge>;
    }
  };

  const getStatusIndicator = (status: string) => {
    switch (status?.toLowerCase()) {
      case "healthy":
      case "good":
      case "active":
        return <div className="w-2 h-2 bg-green-500 rounded-full"></div>;
      case "degraded":
      case "warning":
        return <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>;
      case "error":
      case "failed":
        return <div className="w-2 h-2 bg-red-500 rounded-full"></div>;
      default:
        return <div className="w-2 h-2 bg-gray-500 rounded-full"></div>;
    }
  };

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg font-semibold text-foreground">System Status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {getStatusIndicator(data?.api_health || "healthy")}
              <span className="text-sm text-muted-foreground">API Health</span>
            </div>
            {getStatusBadge(data?.api_health || "healthy")}
          </div>
          
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {getStatusIndicator(data?.rate_limits || "good")}
              <span className="text-sm text-muted-foreground">Rate Limits</span>
            </div>
            {getStatusBadge(data?.rate_limits || "good")}
          </div>
          
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {getStatusIndicator(data?.ethics_guard || "active")}
              <span className="text-sm text-muted-foreground">Ethics Guard</span>
            </div>
            {getStatusBadge(data?.ethics_guard || "active")}
          </div>
        </div>

        <Separator />

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Memory Usage</span>
            <span className="text-sm text-foreground">{data?.memory_usage || "67.2 MB"}</span>
          </div>
          
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Uptime</span>
            <span className="text-sm text-foreground">{data?.uptime || "72h 14m"}</span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Mode</span>
            <Badge 
              variant={data?.live_mode ? "default" : "secondary"}
              className={data?.live_mode 
                ? "bg-green-600 text-white" 
                : "bg-muted text-muted-foreground"
              }
            >
              {data?.live_mode ? "LIVE" : "DRY RUN"}
            </Badge>
          </div>
        </div>

        <Separator />

        <div className="pt-2">
          <h4 className="text-sm font-medium text-foreground mb-3">Next Actions</h4>
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">Reply to mentions in 8min</div>
            <div className="text-xs text-muted-foreground">Post proposal in 23min</div>
            <div className="text-xs text-muted-foreground">Analytics pull in 15min</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
