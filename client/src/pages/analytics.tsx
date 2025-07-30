import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import AnalyticsCharts from "@/components/dashboard/analytics-charts";
import { TrendingUp, TrendingDown, DollarSign, Users, Target, AlertTriangle } from "lucide-react";

export default function Analytics() {
  const { data: analytics, isLoading } = useQuery({
    queryKey: ["/api/analytics"],
    refetchInterval: 60000, // Refresh every minute
  });

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-muted rounded" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-32 bg-muted rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const getChangeIcon = (value: number) => {
    if (value > 0) return <TrendingUp className="h-4 w-4 text-green-600 dark:text-green-400" />;
    if (value < 0) return <TrendingDown className="h-4 w-4 text-red-600 dark:text-red-400" />;
    return null;
  };

  const getChangeColor = (value: number) => {
    if (value > 0) return "text-green-600 dark:text-green-400";
    if (value < 0) return "text-red-600 dark:text-red-400";
    return "text-muted-foreground";
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Analytics Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Comprehensive performance metrics and optimization insights
        </p>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4 bg-muted">
          <TabsTrigger value="overview" className="data-[state=active]:bg-background">Overview</TabsTrigger>
          <TabsTrigger value="objective" className="data-[state=active]:bg-background">Objective Function</TabsTrigger>
          <TabsTrigger value="optimization" className="data-[state=active]:bg-background">Optimization</TabsTrigger>
          <TabsTrigger value="content" className="data-[state=active]:bg-background">Content Analysis</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Fame Score</CardTitle>
                <Target className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{analytics?.fame_score?.toFixed(1) || "0.0"}</div>
                <div className={`text-xs flex items-center mt-1 ${getChangeColor(analytics?.fame_score_change || 0)}`}>
                  {getChangeIcon(analytics?.fame_score_change || 0)}
                  <span className="ml-1">
                    {analytics?.fame_score_change > 0 ? '+' : ''}{analytics?.fame_score_change?.toFixed(1) || '0.0'} from yesterday
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Revenue Today</CardTitle>
                <DollarSign className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">${analytics?.revenue_today?.toFixed(2) || "0.00"}</div>
                <div className={`text-xs flex items-center mt-1 ${getChangeColor(analytics?.revenue_change || 0)}`}>
                  {getChangeIcon(analytics?.revenue_change || 0)}
                  <span className="ml-1">
                    {analytics?.revenue_change > 0 ? '+$' : '-$'}{Math.abs(analytics?.revenue_change || 0).toFixed(2)} from yesterday
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Followers</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{analytics?.follower_count?.toLocaleString() || "0"}</div>
                <div className={`text-xs flex items-center mt-1 ${getChangeColor(analytics?.follower_change || 0)}`}>
                  {getChangeIcon(analytics?.follower_change || 0)}
                  <span className="ml-1">
                    {analytics?.follower_change > 0 ? '+' : ''}{analytics?.follower_change || 0} today
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Engagement Rate</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{analytics?.engagement_rate?.toFixed(1) || "0.0"}%</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Average across last 7 days
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Authority Signals</CardTitle>
                <Badge className="bg-purple-100 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400">
                  {analytics?.authority_signals?.toFixed(1) || "0.0"}
                </Badge>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-muted-foreground">
                  High-quality interactions from verified accounts
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Tweets Today</CardTitle>
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{analytics?.tweets_today || 0}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Posted in last 24 hours
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Performance Summary */}
          <Card>
            <CardHeader>
              <CardTitle>Performance Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="font-medium mb-3">Key Achievements</h3>
                  <ul className="space-y-2 text-sm text-muted-foreground">
                    <li>• Maintained consistent posting schedule</li>
                    <li>• Engaged with {analytics?.tweets_today || 0} conversations</li>
                    <li>• Generated ${analytics?.revenue_today?.toFixed(2) || "0.00"} in tracked revenue</li>
                    <li>• Achieved {analytics?.engagement_rate?.toFixed(1) || "0.0"}% engagement rate</li>
                  </ul>
                </div>
                <div>
                  <h3 className="font-medium mb-3">Optimization Insights</h3>
                  <ul className="space-y-2 text-sm text-muted-foreground">
                    <li>• Best performing content type: Proposals</li>
                    <li>• Optimal posting time: 2-4 PM EST</li>
                    <li>• High-authority engagement trending up</li>
                    <li>• Revenue per click improving</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="objective" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Objective Function Analysis</CardTitle>
              <p className="text-sm text-muted-foreground">
                J = α·FameScore + β·RevenuePerDay + γ·AuthoritySignals − λ·Penalty
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                <div className="text-center">
                  <div className="text-4xl font-bold text-primary">
                    {analytics?.objective_score?.toFixed(1) || "0.0"}
                  </div>
                  <p className="text-sm text-muted-foreground">Current Objective Score</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="text-center p-4 border border-border rounded-lg">
                    <div className="text-2xl font-bold text-blue-600">
                      {analytics?.fame_score?.toFixed(1) || "0.0"}
                    </div>
                    <p className="text-sm text-muted-foreground">Fame Score (α=0.65)</p>
                  </div>
                  <div className="text-center p-4 border border-border rounded-lg">
                    <div className="text-2xl font-bold text-green-600">
                      ${analytics?.revenue_today?.toFixed(2) || "0.00"}
                    </div>
                    <p className="text-sm text-muted-foreground">Revenue (β=0.15)</p>
                  </div>
                  <div className="text-center p-4 border border-border rounded-lg">
                    <div className="text-2xl font-bold text-purple-600">
                      {analytics?.authority_signals?.toFixed(1) || "0.0"}
                    </div>
                    <p className="text-sm text-muted-foreground">Authority (γ=0.25)</p>
                  </div>
                  <div className="text-center p-4 border border-border rounded-lg">
                    <div className="text-2xl font-bold text-orange-600">
                      {analytics?.penalty_score?.toFixed(1) || "0.0"}
                    </div>
                    <p className="text-sm text-muted-foreground">Penalty (λ=0.20)</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="optimization" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>A/B Test Results</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-3 border border-border rounded">
                    <span className="font-medium">Proposal vs Question Posts</span>
                    <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                      Proposals Win
                    </Badge>
                  </div>
                  <div className="flex justify-between items-center p-3 border border-border rounded">
                    <span className="font-medium">Morning vs Evening Posts</span>
                    <Badge className="bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400">
                      Evening Win
                    </Badge>
                  </div>
                  <div className="flex justify-between items-center p-3 border border-border rounded">
                    <span className="font-medium">CTA: Learn More vs Join Pilot</span>
                    <Badge className="bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400">
                      Testing
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Exploration vs Exploitation</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Exploration</span>
                      <span>15%</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div className="bg-orange-500 h-2 rounded-full" style={{ width: "15%" }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Exploitation</span>
                      <span>85%</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div className="bg-primary h-2 rounded-full" style={{ width: "85%" }} />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-4">
                    Optimal balance: Learning from successful patterns while exploring new strategies
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="content" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Top Performing Content</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="border-l-4 border-green-500 pl-4">
                    <h4 className="font-medium">Technology Coordination Proposal</h4>
                    <p className="text-sm text-muted-foreground">J-Score: 0.89 • 45 engagements</p>
                  </div>
                  <div className="border-l-4 border-blue-500 pl-4">
                    <h4 className="font-medium">Energy Grid Mechanism Design</h4>
                    <p className="text-sm text-muted-foreground">J-Score: 0.82 • 38 engagements</p>
                  </div>
                  <div className="border-l-4 border-purple-500 pl-4">
                    <h4 className="font-medium">Governance Innovation Reply</h4>
                    <p className="text-sm text-muted-foreground">J-Score: 0.76 • 29 engagements</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Content Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Proposals</span>
                      <span>70%</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div className="bg-primary h-2 rounded-full" style={{ width: "70%" }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Elite Replies</span>
                      <span>20%</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div className="bg-blue-500 h-2 rounded-full" style={{ width: "20%" }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Summaries</span>
                      <span>10%</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div className="bg-green-500 h-2 rounded-full" style={{ width: "10%" }} />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* Charts Section */}
      <AnalyticsCharts />
    </div>
  );
}
