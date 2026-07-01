import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Brain, RefreshCw } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface ReflectionsResponse {
  count: number;
  lessons: string[];
}

/**
 * The Mind page surfaces the agent's evolving "learned mind": the lessons its
 * nightly reflection loop distils from real performance. These same lessons are
 * fed back into every piece of content the agent generates, so this view is a
 * direct window into how the agent is changing its own behaviour over time.
 */
export default function Mind() {
  const { toast } = useToast();

  const { data, isLoading, isError } = useQuery<ReflectionsResponse>({
    queryKey: ["/api/reflections"],
    queryFn: () => api.get("/api/reflections"),
  });

  const reflectNow = useMutation({
    mutationFn: () => api.post("/api/reflect"),
    onSuccess: (result: any) => {
      toast({
        title: "Reflection complete",
        description: result?.lesson ?? "A new lesson was recorded.",
      });
      queryClient.invalidateQueries({ queryKey: ["/api/reflections"] });
    },
    onError: () => {
      toast({
        title: "Reflection failed",
        description: "Could not run reflection. Check that you are authorised.",
        variant: "destructive",
      });
    },
  });

  const lessons = data?.lessons ?? [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-semibold">The Mind</h1>
            <p className="text-sm text-muted-foreground">
              Lessons the agent has learned and now applies to its own behaviour.
            </p>
          </div>
        </div>
        <Button
          onClick={() => reflectNow.mutate()}
          disabled={reflectNow.isPending}
          data-testid="button-reflect-now"
        >
          <RefreshCw className={"h-4 w-4 mr-2 " + (reflectNow.isPending ? "animate-spin" : "")} />
          {reflectNow.isPending ? "Reflecting..." : "Reflect now"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Learned lessons</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading && (
            <p className="text-sm text-muted-foreground">Loading lessons...</p>
          )}
          {isError && (
            <p className="text-sm text-destructive">Failed to load lessons.</p>
          )}
          {!isLoading && !isError && lessons.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No lessons yet. Run a reflection or let the nightly loop populate this.
            </p>
          )}
          {lessons.map((lesson, idx) => (
            <div
              key={idx}
              className="rounded-md border border-border bg-card/50 p-3 text-sm leading-relaxed"
              data-testid={"lesson-" + idx}
            >
              {lesson}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
