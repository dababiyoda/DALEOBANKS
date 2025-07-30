import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import MonacoEditor from "@/components/ui/monaco-editor";
import { useToast } from "@/hooks/use-toast";
import { Save, Eye, RotateCcw, History, GitBranch } from "lucide-react";
import { useState, useEffect } from "react";

interface PersonaVersion {
  version: number;
  hash: string;
  actor: string;
  created_at: string;
}

export default function PersonaEditor() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [personaContent, setPersonaContent] = useState("");
  const [previewResult, setPreviewResult] = useState<any>(null);

  const { data: persona, isLoading } = useQuery<any>({
    queryKey: ["/api/persona"],
  });

  const { data: versions } = useQuery<PersonaVersion[]>({
    queryKey: ["/api/persona/versions"],
  });

  // Update personaContent when persona data changes
  useEffect(() => {
    if (persona) {
      setPersonaContent(JSON.stringify(persona, null, 2));
    }
  }, [persona]);

  const previewMutation = useMutation({
    mutationFn: (payload: any) => api.post("/api/persona/preview", { payload }),
    onSuccess: (data) => {
      setPreviewResult(data);
      toast({
        title: "Preview Generated",
        description: "Persona validation completed successfully.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Preview Failed",
        description: error.response?.data?.detail || "Failed to validate persona.",
        variant: "destructive",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: any) => api.put("/api/persona", { payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/persona"] });
      queryClient.invalidateQueries({ queryKey: ["/api/persona/versions"] });
      toast({
        title: "Persona Updated",
        description: "Changes have been saved and are now active.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Update Failed",
        description: error.response?.data?.detail || "Failed to update persona.",
        variant: "destructive",
      });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: (version: number) => api.post(`/api/persona/rollback/${version}`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/persona"] });
      queryClient.invalidateQueries({ queryKey: ["/api/persona/versions"] });
      toast({
        title: "Rollback Complete",
        description: "Persona has been rolled back to the selected version.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Rollback Failed",
        description: error.response?.data?.detail || "Failed to rollback persona.",
        variant: "destructive",
      });
    },
  });

  const handlePreview = () => {
    try {
      const payload = JSON.parse(personaContent);
      previewMutation.mutate(payload);
    } catch (error) {
      toast({
        title: "Invalid JSON",
        description: "Please fix the JSON syntax before previewing.",
        variant: "destructive",
      });
    }
  };

  const handleSave = () => {
    try {
      const payload = JSON.parse(personaContent);
      updateMutation.mutate(payload);
    } catch (error) {
      toast({
        title: "Invalid JSON",
        description: "Please fix the JSON syntax before saving.",
        variant: "destructive",
      });
    }
  };

  const handleRollback = (version: number) => {
    rollbackMutation.mutate(version);
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-muted rounded" />
          <div className="h-96 bg-muted rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Persona Editor</h1>
          <p className="text-muted-foreground mt-1">
            Configure the AI agent's personality, behavior, and content strategy
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <Button 
            onClick={handlePreview} 
            variant="outline"
            disabled={previewMutation.isPending}
            className="border-border hover:bg-accent"
          >
            <Eye className="mr-2 h-4 w-4" />
            Preview
          </Button>
          <Button 
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="bg-primary hover:bg-primary/90"
          >
            <Save className="mr-2 h-4 w-4" />
            Save Changes
          </Button>
        </div>
      </div>

      <Tabs defaultValue="editor" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 bg-muted">
          <TabsTrigger value="editor" className="data-[state=active]:bg-background">
            <GitBranch className="mr-2 h-4 w-4" />
            Editor
          </TabsTrigger>
          <TabsTrigger value="preview" className="data-[state=active]:bg-background">
            <Eye className="mr-2 h-4 w-4" />
            Preview
          </TabsTrigger>
          <TabsTrigger value="versions" className="data-[state=active]:bg-background">
            <History className="mr-2 h-4 w-4" />
            Versions
          </TabsTrigger>
        </TabsList>

        <TabsContent value="editor">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Persona Configuration</span>
                <Badge variant="secondary" className="bg-muted text-muted-foreground">
                  Version {persona?.version || 1}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <MonacoEditor
                language="json"
                value={personaContent}
                onChange={setPersonaContent}
                height="600px"
                options={{
                  minimap: { enabled: false },
                  lineNumbers: "on",
                  folding: true,
                  formatOnPaste: true,
                  formatOnType: true,
                }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preview">
          <Card>
            <CardHeader>
              <CardTitle>Validation Preview</CardTitle>
            </CardHeader>
            <CardContent>
              {previewResult ? (
                <div className="space-y-4">
                  {previewResult.valid ? (
                    <div className="p-4 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-lg">
                      <h3 className="font-medium text-green-800 dark:text-green-200 mb-2">
                        ✅ Validation Successful
                      </h3>
                      <p className="text-sm text-green-600 dark:text-green-300">
                        Persona configuration is valid and ready to be saved.
                      </p>
                    </div>
                  ) : (
                    <div className="p-4 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg">
                      <h3 className="font-medium text-red-800 dark:text-red-200 mb-2">
                        ❌ Validation Failed
                      </h3>
                      <ul className="text-sm text-red-600 dark:text-red-300 space-y-1">
                        {previewResult.errors?.map((error: any, index: number) => (
                          <li key={index}>• {error.msg} at {error.loc?.join('.')}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {previewResult.system_prompt_preview && (
                    <div className="space-y-2">
                      <h3 className="font-medium text-foreground">System Prompt Preview</h3>
                      <pre className="text-sm p-4 bg-muted rounded-lg overflow-auto max-h-64 text-muted-foreground">
                        {previewResult.system_prompt_preview}
                      </pre>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <Eye className="mx-auto h-12 w-12 mb-4 opacity-50" />
                  <p>Click "Preview" to validate your persona configuration</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions">
          <Card>
            <CardHeader>
              <CardTitle>Version History</CardTitle>
            </CardHeader>
            <CardContent>
              {versions && versions.length > 0 ? (
                <div className="space-y-4">
                  {versions.map((version: any) => (
                    <div
                      key={version.version}
                      className="flex items-center justify-between p-4 border border-border rounded-lg"
                    >
                      <div className="flex-1">
                        <div className="flex items-center space-x-3">
                          <Badge 
                            variant={version.version === persona?.version ? "default" : "secondary"}
                            className={version.version === persona?.version ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}
                          >
                            v{version.version}
                          </Badge>
                          <span className="text-sm text-muted-foreground">
                            by {version.actor}
                          </span>
                          <span className="text-sm text-muted-foreground">
                            {new Date(version.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          Hash: {version.hash}
                        </p>
                      </div>
                      {version.version !== persona?.version && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleRollback(version.version)}
                          disabled={rollbackMutation.isPending}
                          className="border-border hover:bg-accent"
                        >
                          <RotateCcw className="mr-2 h-4 w-4" />
                          Rollback
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <History className="mx-auto h-12 w-12 mb-4 opacity-50" />
                  <p>No version history available</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
