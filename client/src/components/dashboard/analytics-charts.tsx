import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

export default function AnalyticsCharts() {
  const { data: analytics } = useQuery({
    queryKey: ["/api/analytics"],
  });

  // Mock data for demonstration - in real app this would come from API
  const objectiveData = [
    { time: "00:00", score: 65 },
    { time: "04:00", score: 72 },
    { time: "08:00", score: 68 },
    { time: "12:00", score: 85 },
    { time: "16:00", score: 87 },
    { time: "20:00", score: 83 },
  ];

  const engagementData = [
    { day: "Mon", likes: 234, retweets: 45, replies: 23 },
    { day: "Tue", likes: 345, retweets: 67, replies: 34 },
    { day: "Wed", likes: 456, retweets: 89, replies: 45 },
    { day: "Thu", likes: 567, retweets: 123, replies: 56 },
    { day: "Fri", likes: 678, retweets: 145, replies: 67 },
    { day: "Sat", likes: 543, retweets: 123, replies: 54 },
    { day: "Sun", likes: 432, retweets: 98, replies: 43 },
  ];

  const contentTypeData = [
    { name: "Proposals", value: 70, color: "hsl(207, 90%, 54%)" },
    { name: "Elite Replies", value: 20, color: "hsl(142, 76%, 36%)" },
    { name: "Summaries", value: 10, color: "hsl(262, 83%, 58%)" },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Objective Function Chart */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-foreground">Objective Function (J)</CardTitle>
          <p className="text-sm text-muted-foreground">Fame + Revenue + Authority - Penalties</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={objectiveData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="time" 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <YAxis 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  color: "hsl(var(--foreground))"
                }}
              />
              <Line 
                type="monotone" 
                dataKey="score" 
                stroke="hsl(207, 90%, 54%)" 
                strokeWidth={2}
                dot={{ fill: "hsl(207, 90%, 54%)", strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6, stroke: "hsl(207, 90%, 54%)", strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Engagement Trends Chart */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-foreground">Engagement Trends</CardTitle>
          <p className="text-sm text-muted-foreground">Likes, Retweets, Replies over time</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={engagementData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="day" 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <YAxis 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  color: "hsl(var(--foreground))"
                }}
              />
              <Bar dataKey="likes" fill="hsl(142, 76%, 36%)" radius={[2, 2, 0, 0]} />
              <Bar dataKey="retweets" fill="hsl(207, 90%, 54%)" radius={[2, 2, 0, 0]} />
              <Bar dataKey="replies" fill="hsl(262, 83%, 58%)" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Content Distribution */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-foreground">Content Distribution</CardTitle>
          <p className="text-sm text-muted-foreground">Breakdown by content type</p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={contentTypeData}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
              >
                {contentTypeData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  color: "hsl(var(--foreground))"
                }}
                formatter={(value) => [`${value}%`, "Percentage"]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center space-x-4 mt-4">
            {contentTypeData.map((entry, index) => (
              <div key={index} className="flex items-center space-x-2">
                <div 
                  className="w-3 h-3 rounded-full" 
                  style={{ backgroundColor: entry.color }}
                />
                <span className="text-xs text-muted-foreground">{entry.name}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Performance Metrics */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-foreground">Performance Metrics</CardTitle>
          <p className="text-sm text-muted-foreground">Key performance indicators</p>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Average Engagement</span>
              <span className="text-sm font-medium text-foreground">4.8%</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Response Time</span>
              <span className="text-sm font-medium text-foreground">12 min</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Success Rate</span>
              <span className="text-sm font-medium text-foreground">98.2%</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Daily Posts</span>
              <span className="text-sm font-medium text-foreground">24</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Optimal Hours</span>
              <span className="text-sm font-medium text-foreground">2-4 PM EST</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
