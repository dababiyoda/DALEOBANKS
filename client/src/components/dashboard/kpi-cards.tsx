import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Star, DollarSign, Users, Heart } from "lucide-react";

interface KPIData {
  fame_score?: { value: number };
  revenue_daily?: { value: number };
  follower_growth?: { value: number };
  engagement_rate?: { value: number };
}

interface KPICardsProps {
  data?: KPIData;
}

export default function KPICards({ data }: KPICardsProps) {
  const kpis = [
    {
      title: "Fame Score",
      value: data?.fame_score?.value?.toFixed(1) || "0.0",
      change: "+12.5%",
      trend: "up",
      icon: Star,
      color: "text-blue-600 dark:text-blue-400",
      bgColor: "bg-blue-100 dark:bg-blue-900/20",
    },
    {
      title: "Revenue Today",
      value: `$${data?.revenue_daily?.value?.toFixed(2) || "0.00"}`,
      change: "+$8.20",
      trend: "up",
      icon: DollarSign,
      color: "text-green-600 dark:text-green-400",
      bgColor: "bg-green-100 dark:bg-green-900/20",
    },
    {
      title: "Followers",
      value: (data?.follower_growth?.value || 3247).toLocaleString(),
      change: "+47 today",
      trend: "up",
      icon: Users,
      color: "text-purple-600 dark:text-purple-400",
      bgColor: "bg-purple-100 dark:bg-purple-900/20",
    },
    {
      title: "Engagement Rate",
      value: `${data?.engagement_rate?.value?.toFixed(1) || "4.8"}%`,
      change: "-0.3%",
      trend: "down",
      icon: Heart,
      color: "text-orange-600 dark:text-orange-400",
      bgColor: "bg-orange-100 dark:bg-orange-900/20",
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {kpis.map((kpi) => (
        <Card key={kpi.title} className="border-border">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {kpi.title}
            </CardTitle>
            <div className={`w-12 h-12 ${kpi.bgColor} rounded-lg flex items-center justify-center`}>
              <kpi.icon className={`h-6 w-6 ${kpi.color}`} />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">{kpi.value}</div>
            <div className={`text-sm flex items-center mt-1 ${
              kpi.trend === "up" 
                ? "text-green-600 dark:text-green-400" 
                : "text-red-600 dark:text-red-400"
            }`}>
              {kpi.trend === "up" ? (
                <TrendingUp className="h-4 w-4 mr-1" />
              ) : (
                <TrendingDown className="h-4 w-4 mr-1" />
              )}
              {kpi.change} from yesterday
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
