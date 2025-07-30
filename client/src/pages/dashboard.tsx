import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import KPICards from "@/components/dashboard/kpi-cards";
import ActivityFeed from "@/components/dashboard/activity-feed";
import SystemStatus from "@/components/dashboard/system-status";
import AnalyticsCharts from "@/components/dashboard/analytics-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import { Save, Eye } from "lucide-react";
import { useState } from "react";
import { useToast } from "@/hooks/use-toast";

export default function Dashboard() {
  const { toast } = useToast();
  const [personaMission, setPersonaMission] = useState("");
  const [contentMix, setContentMix] = useState({
    proposals: 70,
    elite_replies: 20,
    summaries: 10
  });

  const { data: dashboardData, isLoading } = useQuery({
    queryKey: ["/api/dashboard"],
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const handleSavePersona = async () => {
    try {
      await api.post("/api/persona/preview", {
        payload: {
          ...dashboardData?.persona_preview,
          mission: personaMission,
          content_mix: {
            proposals: contentMix.proposals / 100,
            elite_replies: contentMix.elite_replies / 100,
            summaries: contentMix.summaries / 100
          }
        }
      });
      toast({
        title: "Persona Updated",
        description: "Persona changes have been saved successfully.",
      });
    } catch (error) {
      toast({
        title: "Update Failed",
        description: "Failed to update persona. Please try again.",
        variant: "destructive",
      });
    }
  };

  const handlePreview = async () => {
    try {
      const response = await api.post("/api/persona/preview", {
        payload: {
          ...dashboardData?.persona_preview,
          mission: personaMission,
          content_mix: {
            proposals: contentMix.proposals / 100,
            elite_replies: contentMix.elite_replies / 100,
            summaries: contentMix.summaries / 100
          }
        }
      });
      toast({
        title: "Preview Generated",
        description: "Check the console for preview output.",
      });
      console.log("Persona Preview:", response);
    } catch (error) {
      toast({
        title: "Preview Failed",
        description: "Failed to generate preview.",
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-32 bg-muted rounded-xl" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 h-64 bg-muted rounded-xl" />
            <div className="h-64 bg-muted rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8">
      {/* KPI Cards */}
      <KPICards data={dashboardData?.kpis} />

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity Feed */}
        <div className="lg:col-span-2">
          <ActivityFeed data={dashboardData?.recent_activity} />
        </div>

        {/* System Status */}
        <div>
          <SystemStatus data={dashboardData?.system_status} />
        </div>
      </div>

      {/* Persona Editor */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Persona Editor</CardTitle>
            <div className="flex items-center space-x-3">
              <Button onClick={handleSavePersona} className="bg-primary hover:bg-primary/90">
                <Save className="mr-2 h-4 w-4" />
                Save
              </Button>
              <Button 
                variant="outline" 
                onClick={handlePreview}
                className="border-border hover:bg-accent"
              >
                <Eye className="mr-2 h-4 w-4" />
                Preview
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <Label htmlFor="mission" className="text-sm font-medium text-foreground">
                Mission Statement
              </Label>
              <Textarea
                id="mission"
                value={personaMission || dashboardData?.persona_preview?.mission || ""}
                onChange={(e) => setPersonaMission(e.target.value)}
                className="mt-2 bg-muted border-border text-foreground placeholder:text-muted-foreground"
                placeholder="Turn critique into deployable mechanisms and pilots."
                rows={4}
              />
            </div>

            <div>
              <Label className="text-sm font-medium text-foreground mb-4 block">
                Content Mix
              </Label>
              <div className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Proposals</span>
                    <span className="text-sm font-medium text-foreground">{contentMix.proposals}%</span>
                  </div>
                  <Slider
                    value={[contentMix.proposals]}
                    onValueChange={(value) => setContentMix(prev => ({ ...prev, proposals: value[0] }))}
                    max={100}
                    step={5}
                    className="w-full"
                  />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Elite Replies</span>
                    <span className="text-sm font-medium text-foreground">{contentMix.elite_replies}%</span>
                  </div>
                  <Slider
                    value={[contentMix.elite_replies]}
                    onValueChange={(value) => setContentMix(prev => ({ ...prev, elite_replies: value[0] }))}
                    max={100}
                    step={5}
                    className="w-full"
                  />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Summaries</span>
                    <span className="text-sm font-medium text-foreground">{contentMix.summaries}%</span>
                  </div>
                  <Slider
                    value={[contentMix.summaries]}
                    onValueChange={(value) => setContentMix(prev => ({ ...prev, summaries: value[0] }))}
                    max={100}
                    step={5}
                    className="w-full"
                  />
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Analytics Charts */}
      <AnalyticsCharts />
    </div>
  );
}
