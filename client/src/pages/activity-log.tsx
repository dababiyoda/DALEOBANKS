import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Search, Filter, Download, RefreshCw } from "lucide-react";
import { useState } from "react";

export default function ActivityLog() {
  const [searchTerm, setSearchTerm] = useState("");
  const [filterType, setFilterType] = useState("all");

  const { data: activities, isLoading, refetch } = useQuery({
    queryKey: ["/api/dashboard"],
    select: (data) => data?.recent_activity || [],
    refetchInterval: 30000,
  });

  const getActivityIcon = (kind: string) => {
    const iconMap: Record<string, string> = {
      proposal_posted: "📝",
      mention_replied: "💬",
      tweet_liked: "❤️",
      tweet_retweeted: "🔄",
      quote_tweeted: "💭",
      follower_snapshot: "📊",
      analytics_updated: "📈",
      nightly_reflection: "🌙",
      weekly_planning: "📅",
      persona_updated: "🎭",
      kpis_calculated: "🎯",
    };
    return iconMap[kind] || "📌";
  };

  const getActivityColor = (kind: string) => {
    const colorMap: Record<string, string> = {
      proposal_posted: "bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400",
      mention_replied: "bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400",
      tweet_liked: "bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400",
      tweet_retweeted: "bg-purple-100 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400",
      analytics_updated: "bg-orange-100 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400",
      nightly_reflection: "bg-indigo-100 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-400",
      persona_updated: "bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400",
    };
    return colorMap[kind] || "bg-gray-100 dark:bg-gray-900/20 text-gray-700 dark:text-gray-400";
  };

  const filteredActivities = activities?.filter((activity: any) => {
    const matchesSearch = activity.kind.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         JSON.stringify(activity.meta).toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterType === "all" || activity.kind.includes(filterType);
    return matchesSearch && matchesFilter;
  }) || [];

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-muted rounded" />
          <div className="space-y-4">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="h-16 bg-muted rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Activity Log</h1>
          <p className="text-muted-foreground mt-1">
            Real-time system activities and agent actions
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => refetch()}
            className="border-border hover:bg-accent"
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button 
            variant="outline" 
            size="sm"
            className="border-border hover:bg-accent"
          >
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search activities..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 bg-background border-border"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select value={filterType} onValueChange={setFilterType}>
                <SelectTrigger className="w-48 border-border">
                  <SelectValue placeholder="Filter by type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Activities</SelectItem>
                  <SelectItem value="posted">Posts & Replies</SelectItem>
                  <SelectItem value="analytics">Analytics</SelectItem>
                  <SelectItem value="reflection">Reflections</SelectItem>
                  <SelectItem value="persona">Persona Changes</SelectItem>
                  <SelectItem value="snapshot">Snapshots</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Activity List */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activities ({filteredActivities.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {filteredActivities.length > 0 ? (
            <div className="space-y-4">
              {filteredActivities.map((activity: any, index: number) => (
                <div
                  key={activity.id || index}
                  className="flex items-start space-x-4 p-4 border border-border rounded-lg hover:bg-accent/50 transition-colors"
                >
                  <div className="flex-shrink-0">
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-lg">
                      {getActivityIcon(activity.kind)}
                    </div>
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <h3 className="text-sm font-medium text-foreground">
                          {activity.kind.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                        </h3>
                        <Badge className={getActivityColor(activity.kind)}>
                          {activity.kind.split('_')[0]}
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(activity.created_at).toLocaleString()}
                      </span>
                    </div>
                    
                    {activity.meta && (
                      <div className="space-y-1">
                        {activity.meta.message && (
                          <p className="text-sm text-muted-foreground">
                            {activity.meta.message}
                          </p>
                        )}
                        
                        {activity.meta.tweet_id && (
                          <div className="text-xs text-muted-foreground">
                            Tweet ID: {activity.meta.tweet_id}
                          </div>
                        )}
                        
                        {activity.meta.topic && (
                          <div className="text-xs text-muted-foreground">
                            Topic: {activity.meta.topic}
                          </div>
                        )}
                        
                        {activity.meta.character_count && (
                          <div className="text-xs text-muted-foreground">
                            Characters: {activity.meta.character_count}/280
                          </div>
                        )}
                        
                        {activity.meta.note && (
                          <div className="text-xs bg-muted p-2 rounded mt-2">
                            {activity.meta.note}
                          </div>
                        )}
                        
                        {activity.meta.count && (
                          <div className="text-xs text-muted-foreground">
                            Count: {activity.meta.count}
                          </div>
                        )}
                        
                        {activity.meta.updated_count && (
                          <div className="text-xs text-muted-foreground">
                            Updated: {activity.meta.updated_count} items
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <div className="text-6xl mb-4">📝</div>
              <h3 className="text-lg font-medium mb-2">No activities found</h3>
              <p className="text-sm">
                {searchTerm || filterType !== "all" 
                  ? "Try adjusting your search or filter criteria"
                  : "System activities will appear here as they occur"
                }
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
