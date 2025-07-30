import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ActivityItem {
  id?: string;
  kind: string;
  meta?: any;
  created_at: string;
}

interface ActivityFeedProps {
  data?: ActivityItem[];
}

export default function ActivityFeed({ data }: ActivityFeedProps) {
  const getActivityIcon = (kind: string) => {
    const iconMap: Record<string, string> = {
      proposal_posted: "📝",
      mention_replied: "💬", 
      tweet_liked: "❤️",
      tweet_retweeted: "🔄",
      quote_tweeted: "💭",
      analytics_updated: "📊",
      nightly_reflection: "🌙",
      weekly_planning: "📅",
      persona_updated: "🎭",
      kpis_calculated: "🎯",
    };
    return iconMap[kind] || "📌";
  };

  const getActivityTitle = (kind: string) => {
    return kind.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
  };

  const getActivityDescription = (activity: ActivityItem) => {
    if (activity.meta?.message) return activity.meta.message;
    if (activity.meta?.tweet_id) return `Tweet ID: ${activity.meta.tweet_id}`;
    if (activity.meta?.topic) return `Topic: ${activity.meta.topic}`;
    return "Activity completed successfully";
  };

  const getStatusBadge = (kind: string) => {
    if (kind.includes('error') || kind.includes('failed')) {
      return <Badge variant="destructive">Error</Badge>;
    }
    if (kind.includes('reflection') || kind.includes('planning')) {
      return <Badge className="bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400">System</Badge>;
    }
    if (kind.includes('posted') || kind.includes('replied')) {
      return <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">Success</Badge>;
    }
    return <Badge className="bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400">Info</Badge>;
  };

  return (
    <Card className="border-border">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold text-foreground">Real-time Activity</CardTitle>
          <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-sm text-muted-foreground">Live</span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-80">
          {data && data.length > 0 ? (
            <div className="space-y-4">
              {data.slice(0, 10).map((activity, index) => (
                <div key={activity.id || index} className="flex items-start space-x-3">
                  <div className="w-8 h-8 bg-muted rounded-full flex items-center justify-center text-sm">
                    {getActivityIcon(activity.kind)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-foreground">
                        {getActivityTitle(activity.kind)}
                      </p>
                      {getStatusBadge(activity.kind)}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {getActivityDescription(activity)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {new Date(activity.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <div className="text-4xl mb-2">🤖</div>
              <p className="text-sm">No recent activities</p>
              <p className="text-xs mt-1">Agent activities will appear here in real-time</p>
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
