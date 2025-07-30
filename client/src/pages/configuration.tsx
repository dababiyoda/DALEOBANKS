import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Settings, Zap, Target, Shield, Clock } from "lucide-react";
import { useState } from "react";

export default function Configuration() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [goalMode, setGoalMode] = useState("FAME");
  const [liveMode, setLiveMode] = useState(true);

  const { data: config, isLoading } = useQuery({
    queryKey: ["/api/dashboard"],
    onSuccess: (data) => {
      setGoalMode(data?.goal_mode || "FAME");
      setLiveMode(data?.system_status?.live_mode || true);
    }
  });

  const toggleLiveMutation = useMutation({
    mutationFn: (live: boolean) => api.post("/api/toggle", { live }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/dashboard"] });
      toast({
        title: "Live Mode Updated",
        description: `Agent is now ${liveMode ? 'active' : 'paused'}.`,
      });
    },
  });

  const setModeMutation = useMutation({
    mutationFn: (mode: string) => api.post("/api/mode", { mode }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/dashboard"] });
      toast({
        title: "Goal Mode Updated",
        description: `Optimization weights adjusted for ${goalMode} mode.`,
      });
    },
  });

  const handleLiveToggle = (checked: boolean) => {
    setLiveMode(checked);
    toggleLiveMutation.mutate(checked);
  };

  const handleModeChange = (mode: string) => {
    setGoalMode(mode);
    setModeMutation.mutate(mode);
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-muted rounded" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-64 bg-muted rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Configuration</h1>
        <p className="text-muted-foreground mt-1">
          Manage agent behavior, optimization settings, and operational parameters
        </p>
      </div>

      <Tabs defaultValue="operation" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4 bg-muted">
          <TabsTrigger value="operation" className="data-[state=active]:bg-background">
            <Zap className="mr-2 h-4 w-4" />
            Operation
          </TabsTrigger>
          <TabsTrigger value="optimization" className="data-[state=active]:bg-background">
            <Target className="mr-2 h-4 w-4" />
            Optimization
          </TabsTrigger>
          <TabsTrigger value="safety" className="data-[state=active]:bg-background">
            <Shield className="mr-2 h-4 w-4" />
            Safety
          </TabsTrigger>
          <TabsTrigger value="schedule" className="data-[state=active]:bg-background">
            <Clock className="mr-2 h-4 w-4" />
            Schedule
          </TabsTrigger>
        </TabsList>

        <TabsContent value="operation" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Live Mode Control */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Live Mode Control</span>
                  <Badge 
                    variant={liveMode ? "default" : "secondary"}
                    className={liveMode ? "bg-green-600 text-white" : "bg-muted text-muted-foreground"}
                  >
                    {liveMode ? "ACTIVE" : "PAUSED"}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <Label htmlFor="live-mode" className="text-sm font-medium">
                      Enable Live Posting
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      When enabled, the agent will post to Twitter/X in real-time
                    </p>
                  </div>
                  <Switch
                    id="live-mode"
                    checked={liveMode}
                    onCheckedChange={handleLiveToggle}
                    disabled={toggleLiveMutation.isPending}
                  />
                </div>
                <div className="pt-4 border-t border-border">
                  <p className="text-sm text-muted-foreground">
                    {liveMode 
                      ? "Agent is actively posting and engaging on social media" 
                      : "Agent is in dry-run mode - content is generated but not posted"
                    }
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Goal Mode */}
            <Card>
              <CardHeader>
                <CardTitle>Goal Mode</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="goal-mode" className="text-sm font-medium">
                    Optimization Focus
                  </Label>
                  <Select value={goalMode} onValueChange={handleModeChange}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select goal mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="FAME">FAME - Maximize Engagement</SelectItem>
                      <SelectItem value="MONETIZE">MONETIZE - Maximize Revenue</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Current weights:</p>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>Fame: {goalMode === "FAME" ? "65%" : "30%"}</div>
                    <div>Revenue: {goalMode === "FAME" ? "15%" : "55%"}</div>
                    <div>Authority: 25%</div>
                    <div>Penalty: {goalMode === "FAME" ? "20%" : "25%"}</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Feature Toggles */}
            <Card>
              <CardHeader>
                <CardTitle>Feature Toggles</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {[
                  { key: "likes", label: "Likes", description: "Like relevant tweets" },
                  { key: "reposts", label: "Reposts", description: "Repost high-quality content" },
                  { key: "quotes", label: "Quote Tweets", description: "Quote tweet with commentary" },
                  { key: "follows", label: "Follows", description: "Follow relevant accounts" },
                  { key: "bookmarks", label: "Bookmarks", description: "Bookmark valuable content" },
                  { key: "dms", label: "Direct Messages", description: "Send direct messages" },
                  { key: "media", label: "Media Upload", description: "Upload images and videos" },
                ].map((feature) => (
                  <div key={feature.key} className="flex items-center justify-between">
                    <div className="space-y-1">
                      <Label className="text-sm font-medium">{feature.label}</Label>
                      <p className="text-xs text-muted-foreground">{feature.description}</p>
                    </div>
                    <Switch defaultChecked />
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* API Status */}
            <Card>
              <CardHeader>
                <CardTitle>API Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Twitter/X API</span>
                    <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                      Connected
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm">OpenAI API</span>
                    <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                      Connected
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Rate Limits</span>
                    <Badge className="bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400">
                      Healthy
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="optimization" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Objective Function Weights</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <Label className="text-sm font-medium">Fame Score (α)</Label>
                  <div className="mt-2">
                    <Slider defaultValue={[goalMode === "FAME" ? 65 : 30]} max={100} step={5} />
                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                      <span>0%</span>
                      <span>100%</span>
                    </div>
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-medium">Revenue (β)</Label>
                  <div className="mt-2">
                    <Slider defaultValue={[goalMode === "FAME" ? 15 : 55]} max={100} step={5} />
                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                      <span>0%</span>
                      <span>100%</span>
                    </div>
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-medium">Authority (γ)</Label>
                  <div className="mt-2">
                    <Slider defaultValue={[25]} max={100} step={5} />
                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                      <span>0%</span>
                      <span>100%</span>
                    </div>
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-medium">Penalty (λ)</Label>
                  <div className="mt-2">
                    <Slider defaultValue={[goalMode === "FAME" ? 20 : 25]} max={100} step={5} />
                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                      <span>0%</span>
                      <span>100%</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Learning Parameters</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Exploration Rate (ε)</Label>
                  <Slider defaultValue={[10]} max={50} step={1} />
                  <p className="text-xs text-muted-foreground">
                    Minimum exploration probability: 10%
                  </p>
                </div>
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Learning Window</Label>
                  <Select defaultValue="7days">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="3days">3 Days</SelectItem>
                      <SelectItem value="7days">7 Days</SelectItem>
                      <SelectItem value="14days">14 Days</SelectItem>
                      <SelectItem value="30days">30 Days</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="safety" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Ethics Guardrails</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {[
                  { name: "No Harm", status: "active", description: "Prevent harmful content generation" },
                  { name: "No Deception", status: "active", description: "Block misleading information" },
                  { name: "Uncertainty Quantification", status: "active", description: "Include uncertainty in proposals" },
                  { name: "Rollback Plans", status: "active", description: "Require rollback conditions" },
                ].map((guardrail) => (
                  <div key={guardrail.name} className="flex items-center justify-between p-3 border border-border rounded">
                    <div>
                      <div className="font-medium text-sm">{guardrail.name}</div>
                      <div className="text-xs text-muted-foreground">{guardrail.description}</div>
                    </div>
                    <Badge className="bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                      {guardrail.status}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Rate Limiting</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm">API Calls/Hour</span>
                    <span className="text-sm font-medium">45/100</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div className="bg-primary h-2 rounded-full" style={{ width: "45%" }} />
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm">Posts/Hour</span>
                    <span className="text-sm font-medium">3/5</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: "60%" }} />
                  </div>
                </div>
                <div className="pt-2 text-xs text-muted-foreground">
                  Automatic backoff and circuit breakers prevent rate limit violations
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="schedule" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Posting Schedule</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm">Post Proposals</span>
                    <span className="text-sm text-muted-foreground">Every 45-90min</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm">Reply to Mentions</span>
                    <span className="text-sm text-muted-foreground">Every 12-25min</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm">Search & Engage</span>
                    <span className="text-sm text-muted-foreground">Every 25-45min</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm">Analytics Pull</span>
                    <span className="text-sm text-muted-foreground">Every 35-60min</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Quiet Hours</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Enable Quiet Hours</Label>
                  <Switch />
                </div>
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Start Time (ET)</Label>
                  <Select defaultValue="1am">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 24 }, (_, i) => (
                        <SelectItem key={i} value={`${i}${i === 0 ? 'am' : i < 12 ? 'am' : 'pm'}`}>
                          {i === 0 ? '12am' : i <= 12 ? `${i}am` : `${i-12}pm`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-sm font-medium">End Time (ET)</Label>
                  <Select defaultValue="6am">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 24 }, (_, i) => (
                        <SelectItem key={i} value={`${i}${i === 0 ? 'am' : i < 12 ? 'am' : 'pm'}`}>
                          {i === 0 ? '12am' : i <= 12 ? `${i}am` : `${i-12}pm`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
