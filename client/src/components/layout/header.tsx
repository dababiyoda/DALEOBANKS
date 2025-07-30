import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useTheme } from "@/components/ui/theme-provider";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Moon, Sun, User } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function Header() {
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: dashboardData } = useQuery({
    queryKey: ["/api/dashboard"],
  });

  const toggleLiveMutation = useMutation({
    mutationFn: (live: boolean) => api.post("/api/toggle", { live }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/dashboard"] });
      toast({
        title: "Live Mode Updated",
        description: `Agent is now ${dashboardData?.system_status?.live_mode ? 'paused' : 'active'}.`,
      });
    },
  });

  const isLive = dashboardData?.system_status?.live_mode || false;

  const handleLiveToggle = (checked: boolean) => {
    toggleLiveMutation.mutate(checked);
  };

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
  };

  return (
    <header className="bg-card border-b border-border sticky top-0 z-50">
      <div className="px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            {/* Current page would be shown here dynamically */}
          </div>
          
          <div className="flex items-center space-x-6">
            {/* LIVE Toggle */}
            <div className="flex items-center space-x-3">
              <Label htmlFor="live-toggle" className="text-sm font-medium text-foreground">
                LIVE Mode
              </Label>
              <Switch
                id="live-toggle"
                checked={isLive}
                onCheckedChange={handleLiveToggle}
                disabled={toggleLiveMutation.isPending}
              />
              <Badge 
                variant={isLive ? "default" : "secondary"}
                className={isLive 
                  ? "bg-green-600 hover:bg-green-700 text-white" 
                  : "bg-muted text-muted-foreground"
                }
              >
                {isLive ? "ACTIVE" : "PAUSED"}
              </Badge>
            </div>
            
            {/* Theme Toggle */}
            <Button
              variant="outline"
              size="sm"
              onClick={toggleTheme}
              className="border-border hover:bg-accent"
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </Button>
            
            {/* Profile */}
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-muted rounded-full flex items-center justify-center">
                <User className="h-4 w-4 text-muted-foreground" />
              </div>
              <span className="text-sm font-medium text-foreground">Admin</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
