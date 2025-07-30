import { Switch, Route } from "wouter";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/queryClient";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/ui/theme-provider";

// Pages
import Dashboard from "@/pages/dashboard";
import PersonaEditor from "@/pages/persona-editor";
import Analytics from "@/pages/analytics";
import Configuration from "@/pages/configuration";
import ActivityLog from "@/pages/activity-log";
import Health from "@/pages/health";
import NotFound from "@/pages/not-found";

// Layout components
import Header from "@/components/layout/header";
import Sidebar from "@/components/layout/sidebar";

function Router() {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto">
          <Switch>
            <Route path="/" component={Dashboard} />
            <Route path="/persona" component={PersonaEditor} />
            <Route path="/analytics" component={Analytics} />
            <Route path="/config" component={Configuration} />
            <Route path="/logs" component={ActivityLog} />
            <Route path="/health" component={Health} />
            <Route component={NotFound} />
          </Switch>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider defaultTheme="light" storageKey="daleobanks-theme">
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
