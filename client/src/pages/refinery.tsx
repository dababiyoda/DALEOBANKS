import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { getAdminJwt, setAdminJwt } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import {
  Check,
  X,
  KeyRound,
  LogOut,
  Lightbulb,
  Rocket,
  Scale,
  Clapperboard,
  Route,
  Send,
  Wand2,
} from "lucide-react";

interface Idea {
  id: string;
  raw_text: string;
  thesis: string;
  audiences: Array<Record<string, string>>;
  status: string;
  risk_flags: string[];
  created_at: string;
}

interface Opportunity {
  id: string;
  signal_type: string;
  observed_pain: string;
  core_thesis: string;
  audience: string;
  urgency: string;
  evidence: string[];
  possible_offer: string;
  monetization_paths: string[];
  risk_flags: string[];
  smallest_validation_action: string;
  confidence: number;
  status: string;
  created_at: string;
}

interface Assessment {
  id: string;
  opportunity_packet_id: string;
  go_no_go: string;
  opportunity_score: number;
  market_alignment: number;
  risk_level: string;
  legal_readiness: string;
  pricing_hypothesis: string;
  validation_plan: string[];
  recommended_next_action: string;
  reasons: string[];
  created_at: string;
}

interface MediaDraft {
  id: string;
  format: string;
  platform: string;
  language: string;
  account_lane: string;
  cultural_context: string;
  title: string;
  draft_text: string;
  script: string;
  hook: string;
  cta: string;
  disclosure_needed: boolean;
  risk_level: string;
  approval_status: string;
  created_at: string;
}

interface Lane {
  id: string;
  name: string;
  platform: string;
  identity_type: string;
  purpose: string;
  audience: string;
  language: string;
  cultural_context: string;
  allowed_topics: string[];
  forbidden_topics: string[];
  approval_required: boolean;
  active: boolean;
}

const GO_COLORS: Record<string, string> = {
  go: "bg-green-500/15 text-green-700 dark:text-green-400",
  defer: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  kill: "bg-red-500/15 text-red-700 dark:text-red-400",
  needs_more_evidence: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
};

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
          Intake, refinement, and decisions change what the machine prepares.
          Paste the ADMIN_TOKEN to mint a 12-hour admin session.
        </p>
        <Label htmlFor="refinery-admin-token">Admin token</Label>
        <Input
          id="refinery-admin-token"
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

export default function Refinery() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [unlocked, setUnlocked] = useState(() => Boolean(getAdminJwt()));
  const [thought, setThought] = useState("");
  const [draftFilter, setDraftFilter] = useState("pending");

  const handleAuthFailure = () => {
    setAdminJwt(null);
    setUnlocked(false);
    toast({
      title: "Session expired",
      description: "Unlock again with the admin token.",
      variant: "destructive",
    });
  };

  const { data: ideas } = useQuery<{ count: number; ideas: Idea[] }>({
    queryKey: ["/api/ideas"],
    refetchInterval: 30000,
  });
  const { data: opportunities } = useQuery<{ count: number; opportunities: Opportunity[] }>({
    queryKey: ["/api/opportunities"],
    refetchInterval: 30000,
  });
  const { data: assessments } = useQuery<{ count: number; assessments: Assessment[] }>({
    queryKey: ["/api/assessments"],
    refetchInterval: 30000,
  });
  const { data: drafts } = useQuery<{ count: number; drafts: MediaDraft[] }>({
    queryKey: [`/api/media/drafts?status_filter=${draftFilter}`],
    refetchInterval: 30000,
  });
  const { data: lanes } = useQuery<{ count: number; policy: string[]; lanes: Lane[] }>({
    queryKey: ["/api/lanes"],
  });

  const intakeIdea = useMutation({
    mutationFn: (text: string) => api.post("/api/ideas/intake", { text, refine: true }),
    onSuccess: () => {
      setThought("");
      queryClient.invalidateQueries({ queryKey: ["/api/ideas"] });
      queryClient.invalidateQueries({ queryKey: ["/api/opportunities"] });
      queryClient.invalidateQueries({
        queryKey: [`/api/media/drafts?status_filter=${draftFilter}`],
      });
      toast({
        title: "Idea refined",
        description: "Thesis, audiences, drafts, and any opportunity packet are ready for review.",
      });
    },
    onError: handleAuthFailure,
  });

  const refineIdea = useMutation({
    mutationFn: (id: string) => api.post(`/api/ideas/${id}/refine`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/ideas"] });
      queryClient.invalidateQueries({ queryKey: ["/api/opportunities"] });
      toast({ title: "Refined", description: "New drafts are waiting in Media Drafts." });
    },
    onError: handleAuthFailure,
  });

  const decideOpportunity = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api.post(`/api/opportunities/${id}/decision`, { approve }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["/api/opportunities"] });
      toast({
        title: variables.approve ? "Approved" : "Rejected",
        description: variables.approve
          ? "Approved packets can be sent to WealthMachine for evaluation."
          : "The packet was declined.",
      });
    },
    onError: handleAuthFailure,
  });

  const sendToWealthMachine = useMutation({
    mutationFn: (id: string) => api.post(`/api/opportunities/${id}/send-to-wealthmachine`),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/opportunities"] });
      queryClient.invalidateQueries({ queryKey: ["/api/assessments"] });
      queryClient.invalidateQueries({
        queryKey: [`/api/media/drafts?status_filter=${draftFilter}`],
      });
      toast({
        title: `Assessment: ${data.assessment?.go_no_go ?? "received"}`,
        description:
          "Validation drafts were created and an approval request was queued. Nothing runs without your yes.",
      });
    },
    onError: handleAuthFailure,
  });

  const decideDraft = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api.post(`/api/media/drafts/${id}/decision`, { approve }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [`/api/media/drafts?status_filter=${draftFilter}`],
      });
      toast({
        title: "Recorded",
        description: "Approved drafts still publish only through the gated pipelines.",
      });
    },
    onError: handleAuthFailure,
  });

  const ideaList = ideas?.ideas ?? [];
  const oppList = opportunities?.opportunities ?? [];
  const assessmentList = assessments?.assessments ?? [];
  const draftList = drafts?.drafts ?? [];
  const laneList = lanes?.lanes ?? [];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Idea Refinery</h1>
          <p className="text-muted-foreground mt-1">
            The machine prepares. You authorize. Raw thoughts become theses,
            localized drafts, opportunity packets, and venture assessments —
            nothing external happens without approval.
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

      <Tabs defaultValue="ideas">
        <TabsList>
          <TabsTrigger value="ideas">
            <Lightbulb className="mr-2 h-4 w-4" /> Ideas ({ideaList.length})
          </TabsTrigger>
          <TabsTrigger value="opportunities">
            <Rocket className="mr-2 h-4 w-4" /> Opportunities ({oppList.length})
          </TabsTrigger>
          <TabsTrigger value="assessments">
            <Scale className="mr-2 h-4 w-4" /> Assessments ({assessmentList.length})
          </TabsTrigger>
          <TabsTrigger value="drafts">
            <Clapperboard className="mr-2 h-4 w-4" /> Media Drafts ({draftList.length})
          </TabsTrigger>
          <TabsTrigger value="lanes">
            <Route className="mr-2 h-4 w-4" /> Account Lanes ({laneList.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="ideas" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Drop a raw thought</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                value={thought}
                onChange={(e) => setThought(e.target.value)}
                placeholder="Financial independence is not selfish. It is protection from systems that profit from dependency."
                rows={3}
              />
              <Button
                disabled={!unlocked || !thought.trim() || intakeIdea.isPending}
                onClick={() => intakeIdea.mutate(thought.trim())}
              >
                <Wand2 className="mr-2 h-4 w-4" /> Intake &amp; refine
              </Button>
            </CardContent>
          </Card>

          {ideaList.map((idea) => (
            <Card key={idea.id}>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{idea.status}</Badge>
                    {idea.risk_flags.map((flag) => (
                      <Badge key={flag} variant="destructive">{flag}</Badge>
                    ))}
                  </div>
                  {idea.status === "pending" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!unlocked || refineIdea.isPending}
                      onClick={() => refineIdea.mutate(idea.id)}
                    >
                      <Wand2 className="mr-2 h-4 w-4" /> Refine
                    </Button>
                  )}
                </div>
                <p className="text-sm">{idea.raw_text}</p>
                {idea.thesis && (
                  <p className="text-sm font-medium">Thesis: {idea.thesis}</p>
                )}
                {idea.audiences.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {idea.audiences.map((a, i) => (
                      <Badge key={i} variant="outline">
                        {a.name} · {a.language}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
          {ideaList.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No ideas yet. Drop a thought above — the refinery extracts the
              thesis, recommends audiences, and drafts localized media.
            </p>
          )}
        </TabsContent>

        <TabsContent value="opportunities" className="space-y-4">
          {oppList.map((opp) => (
            <Card key={opp.id}>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{opp.status}</Badge>
                    <Badge variant="outline">{opp.signal_type}</Badge>
                    <Badge variant="outline">urgency: {opp.urgency}</Badge>
                    {opp.risk_flags.map((flag) => (
                      <Badge key={flag} variant="destructive">{flag}</Badge>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    {opp.status === "pending" && (
                      <>
                        <Button
                          size="sm"
                          disabled={!unlocked || decideOpportunity.isPending}
                          onClick={() => decideOpportunity.mutate({ id: opp.id, approve: true })}
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!unlocked || decideOpportunity.isPending}
                          onClick={() => decideOpportunity.mutate({ id: opp.id, approve: false })}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                    {opp.status === "approved" && (
                      <Button
                        size="sm"
                        disabled={!unlocked || sendToWealthMachine.isPending}
                        onClick={() => sendToWealthMachine.mutate(opp.id)}
                      >
                        <Send className="mr-2 h-4 w-4" /> Send to WealthMachine
                      </Button>
                    )}
                  </div>
                </div>
                <p className="text-sm font-medium">{opp.core_thesis}</p>
                <p className="text-sm text-muted-foreground">Pain: {opp.observed_pain}</p>
                <p className="text-sm">
                  Offer: {opp.possible_offer || "—"} · Audience: {opp.audience}
                </p>
                <p className="text-xs text-muted-foreground">
                  Evidence: {opp.evidence.join("; ") || "none"} · Confidence:{" "}
                  {opp.confidence}
                </p>
                <p className="text-xs">
                  Smallest validation action: {opp.smallest_validation_action}
                </p>
              </CardContent>
            </Card>
          ))}
          {oppList.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No opportunity packets yet. Refined ideas with a plausible offer
              land here for your approve/reject before any evaluation.
            </p>
          )}
        </TabsContent>

        <TabsContent value="assessments" className="space-y-4">
          {assessmentList.map((a) => (
            <Card key={a.id}>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge className={GO_COLORS[a.go_no_go] ?? ""}>{a.go_no_go}</Badge>
                  <Badge variant="outline">score {a.opportunity_score}</Badge>
                  <Badge variant="outline">risk {a.risk_level}</Badge>
                  <Badge variant="outline">legal {a.legal_readiness}</Badge>
                </div>
                <p className="text-sm">Pricing hypothesis: {a.pricing_hypothesis}</p>
                <p className="text-sm">Next action: {a.recommended_next_action}</p>
                {a.validation_plan.length > 0 && (
                  <ol className="text-sm text-muted-foreground list-decimal ml-5">
                    {a.validation_plan.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                )}
                <p className="text-xs text-muted-foreground">
                  {a.reasons.join(" · ")}
                </p>
              </CardContent>
            </Card>
          ))}
          {assessmentList.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No assessments yet. Approve an opportunity and send it to
              WealthMachine — its go/defer/kill verdict lands here.
            </p>
          )}
        </TabsContent>

        <TabsContent value="drafts" className="space-y-4">
          <div className="flex gap-2">
            {["pending", "approved", "rejected"].map((s) => (
              <Button
                key={s}
                size="sm"
                variant={draftFilter === s ? "default" : "outline"}
                onClick={() => setDraftFilter(s)}
              >
                {s}
              </Button>
            ))}
          </div>
          {draftList.map((d) => (
            <Card key={d.id}>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="secondary">{d.format}</Badge>
                    <Badge variant="outline">{d.platform}</Badge>
                    <Badge variant="outline">{d.language}</Badge>
                    <Badge variant="outline">lane: {d.account_lane}</Badge>
                    <Badge variant="outline">risk: {d.risk_level}</Badge>
                    {d.disclosure_needed && (
                      <Badge variant="destructive">disclosure required</Badge>
                    )}
                  </div>
                  {d.approval_status === "pending" && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={!unlocked || decideDraft.isPending}
                        onClick={() => decideDraft.mutate({ id: d.id, approve: true })}
                      >
                        <Check className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!unlocked || decideDraft.isPending}
                        onClick={() => decideDraft.mutate({ id: d.id, approve: false })}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
                <p className="text-sm font-medium">{d.title}</p>
                {d.hook && <p className="text-sm italic">{d.hook}</p>}
                <pre className="text-sm whitespace-pre-wrap text-muted-foreground">
                  {d.draft_text || d.script}
                </pre>
                {d.cta && <p className="text-xs">CTA: {d.cta}</p>}
              </CardContent>
            </Card>
          ))}
          {draftList.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No {draftFilter} drafts. Approving a draft marks it publishable —
              actual publishing still runs through the gated pipelines.
            </p>
          )}
        </TabsContent>

        <TabsContent value="lanes" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Hardcoded lane policy</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="text-sm text-muted-foreground list-disc ml-5 space-y-1">
                {(lanes?.policy ?? []).map((rule, i) => (
                  <li key={i}>{rule}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
          {laneList.map((lane) => (
            <Card key={lane.id}>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{lane.name}</span>
                  <Badge variant="secondary">{lane.identity_type}</Badge>
                  <Badge variant="outline">{lane.platform}</Badge>
                  <Badge variant="outline">{lane.language}</Badge>
                  <Badge variant={lane.active ? "default" : "outline"}>
                    {lane.active ? "active" : "inactive"}
                  </Badge>
                  {lane.approval_required && (
                    <Badge variant="outline">approval required</Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {lane.purpose} — {lane.audience}
                </p>
                <p className="text-xs text-muted-foreground">
                  Topics: {lane.allowed_topics.join(", ") || "—"} · Forbidden:{" "}
                  {lane.forbidden_topics.join(", ") || "—"}
                </p>
              </CardContent>
            </Card>
          ))}
          {laneList.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No account lanes yet. Lanes are distinct authentic brands or
              project pages — never fake people. Create them via the API; the
              identity gate rejects inauthentic identity types outright.
            </p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
