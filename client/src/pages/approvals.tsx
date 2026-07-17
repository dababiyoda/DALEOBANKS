import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { getAdminJwt, setAdminJwt } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Check, X, KeyRound, LogOut, Compass, Target, ShieldCheck, History } from "lucide-react";

interface OperatorRequest {
  id: string;
  code: string;
  kind: string;
  priority: string;
  summary: string;
  rationale: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: string;
}

interface DiscoveryProposal {
  id: string;
  kind: string;
  value: string;
  evidence: Record<string, unknown>;
  status: string;
  created_at: string;
}

interface GoalProposal {
  id: string;
  proposal: Record<string, unknown>;
  rationale: string;
  status: string;
  created_at: string;
}

function AdminUnlock({ onUnlocked }: { onUnlocked: () => void }) {
  const { toast } = useToast();
  const [adminToken, setAdminToken] = useState("");
  const [busy, setBusy] = useState(false);

  const unlock = async () => {
    setBusy(true);
    try {
      const response = await api.post("/api/auth/token", { admin_token: adminToken });
      setAdminJwt(response.token);
      setAdminToken("");
      toast({ title: "Unlocked", description: "Admin session active for 12 hours." });
      onUnlocked();
    } catch {
      toast({
        title: "Unlock failed",
        description: "That admin token was not accepted.",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-4 w-4" /> Admin unlock
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Approvals change what the agent is allowed to become. Paste the
          ADMIN_TOKEN (from your secrets) to mint a 12-hour admin session.
        </p>
        <Label htmlFor="admin-token">Admin token</Label>
        <Input
          id="admin-token"
          type="password"
          value={adminToken}
          onChange={(e) => setAdminToken(e.target.value)}
          placeholder="ADMIN_TOKEN"
        />
        <Button onClick={unlock} disabled={busy || !adminToken}>
          Unlock
        </Button>
      </CardContent>
    </Card>
  );
}

export default function Approvals() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [unlocked, setUnlocked] = useState(() => Boolean(getAdminJwt()));

  const { data: discoveries } = useQuery<{ count: number; proposals: DiscoveryProposal[] }>({
    queryKey: ["/api/discoveries"],
    refetchInterval: 30000,
  });

  const { data: goals } = useQuery<{ count: number; proposals: GoalProposal[] }>({
    queryKey: ["/api/goals/proposals"],
    refetchInterval: 30000,
  });

  const { data: operatorPending } = useQuery<{ count: number; requests: OperatorRequest[] }>({
    queryKey: ["/api/operator/requests?status_filter=pending"],
    refetchInterval: 30000,
  });

  const { data: operatorApproved } = useQuery<{ count: number; requests: OperatorRequest[] }>({
    queryKey: ["/api/operator/requests?status_filter=approved"],
    refetchInterval: 60000,
  });

  const { data: operatorRejected } = useQuery<{ count: number; requests: OperatorRequest[] }>({
    queryKey: ["/api/operator/requests?status_filter=rejected"],
    refetchInterval: 60000,
  });

  const handleAuthFailure = () => {
    setAdminJwt(null);
    setUnlocked(false);
    toast({
      title: "Session expired",
      description: "Unlock again with the admin token.",
      variant: "destructive",
    });
  };

  const decideDiscovery = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api.post(`/api/discoveries/${id}/decision`, { approve }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["/api/discoveries"] });
      toast({
        title: variables.approve ? "Approved" : "Rejected",
        description: variables.approve
          ? "The agent's perception will widen on its next scan."
          : "The proposal was declined.",
      });
    },
    onError: handleAuthFailure,
  });

  const decideGoal = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api.post(`/api/goals/proposals/${id}/decision`, { approve }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["/api/goals/proposals"] });
      toast({
        title: variables.approve ? "Approved" : "Rejected",
        description: variables.approve
          ? "The new OKR takes effect at the next planning cycle."
          : "The proposal was declined.",
      });
    },
    onError: handleAuthFailure,
  });

  const decideOperator = useMutation({
    mutationFn: ({ code, approve }: { code: string; approve: boolean }) =>
      api.post("/api/operator/command", {
        command: `${approve ? "YES" : "NO"} ${code}`,
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["/api/operator/requests?status_filter=pending"],
      });
      queryClient.invalidateQueries({
        queryKey: ["/api/operator/requests?status_filter=approved"],
      });
      queryClient.invalidateQueries({
        queryKey: ["/api/operator/requests?status_filter=rejected"],
      });
      toast({
        title: variables.approve ? "Approved" : "Rejected",
        description: variables.approve
          ? "Exactly this request was authorized — approval never widens standing autonomy."
          : "The request was declined.",
      });
    },
    onError: handleAuthFailure,
  });

  const pendingDiscoveries = discoveries?.proposals ?? [];
  const pendingGoals = goals?.proposals ?? [];
  const pendingOperator = operatorPending?.requests ?? [];
  const decidedOperator = [
    ...(operatorApproved?.requests ?? []),
    ...(operatorRejected?.requests ?? []),
  ].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 20);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Approvals</h1>
          <p className="text-muted-foreground mt-1">
            The agent proposes; you decide. Nothing here takes effect without you.
          </p>
        </div>
        {unlocked && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setAdminJwt(null);
              setUnlocked(false);
            }}
          >
            <LogOut className="mr-2 h-4 w-4" /> Lock
          </Button>
        )}
      </div>

      {!unlocked && <AdminUnlock onUnlocked={() => setUnlocked(true)} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            Risky actions awaiting your code
            <Badge variant="secondary">{pendingOperator.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pendingOperator.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing pending. Public posting, outreach, paid offers, and
              validation plans all queue here — each with a one-time approval
              code, answerable here or by SMS.
            </p>
          ) : (
            <div className="space-y-3">
              {pendingOperator.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between p-3 border border-border rounded-lg"
                >
                  <div className="pr-4">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge>{r.kind}</Badge>
                      <Badge variant="outline">{r.priority}</Badge>
                      <Badge variant="secondary" className="font-mono">
                        {r.code}
                      </Badge>
                      <span className="font-medium">{r.summary}</span>
                    </div>
                    {r.rationale && (
                      <p className="text-xs text-muted-foreground mt-1">{r.rationale}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={!unlocked || decideOperator.isPending}
                      onClick={() => decideOperator.mutate({ code: r.code, approve: true })}
                    >
                      <Check className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!unlocked || decideOperator.isPending}
                      onClick={() => decideOperator.mutate({ code: r.code, approve: false })}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-4 w-4" />
            Decision history
            <Badge variant="secondary">{decidedOperator.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {decidedOperator.length === 0 ? (
            <p className="text-sm text-muted-foreground">No decisions recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {decidedOperator.map((r) => (
                <div key={r.id} className="flex items-center gap-2 text-sm">
                  <Badge variant={r.status === "approved" ? "default" : "outline"}>
                    {r.status}
                  </Badge>
                  <Badge variant="outline">{r.kind}</Badge>
                  <span className="text-muted-foreground">{r.summary}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Compass className="h-4 w-4" />
            Discovery proposals
            <Badge variant="secondary">{pendingDiscoveries.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pendingDiscoveries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No pending proposals. The daily discovery job files new voices and
              keywords here when real engagement earns them.
            </p>
          ) : (
            <div className="space-y-3">
              {pendingDiscoveries.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between p-3 border border-border rounded-lg"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge>{p.kind}</Badge>
                      <span className="font-medium">{p.value}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {JSON.stringify(p.evidence)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={!unlocked || decideDiscovery.isPending}
                      onClick={() => decideDiscovery.mutate({ id: p.id, approve: true })}
                    >
                      <Check className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!unlocked || decideDiscovery.isPending}
                      onClick={() => decideDiscovery.mutate({ id: p.id, approve: false })}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-4 w-4" />
            Goal proposals
            <Badge variant="secondary">{pendingGoals.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pendingGoals.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No pending proposals. The planner files OKR adjustments here when
              performance suggests raising or reducing ambition.
            </p>
          ) : (
            <div className="space-y-3">
              {pendingGoals.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between p-3 border border-border rounded-lg"
                >
                  <div className="pr-4">
                    <p className="text-sm font-medium">{p.rationale}</p>
                    <pre className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">
                      {JSON.stringify(p.proposal, null, 2)}
                    </pre>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={!unlocked || decideGoal.isPending}
                      onClick={() => decideGoal.mutate({ id: p.id, approve: true })}
                    >
                      <Check className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!unlocked || decideGoal.isPending}
                      onClick={() => decideGoal.mutate({ id: p.id, approve: false })}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
