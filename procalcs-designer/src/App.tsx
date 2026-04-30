import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthGuard } from "@/components/auth-guard";
import NotFound from "@/pages/not-found";

import { Layout } from "@/components/layout";
import Dashboard from "@/pages/dashboard";
import ProfilesList from "@/pages/profiles/index";
import NewProfile from "@/pages/profiles/new";
import EditProfile from "@/pages/profiles/detail";
import BomEngine from "@/pages/bom-engine";
import BomOutput from "@/pages/bom-output";
import SkuCatalogPage from "@/pages/sku-catalog";
import RulesPreviewPage from "@/pages/diagnostics/rules-preview";

const queryClient = new QueryClient();

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/" component={Dashboard} />
        <Route path="/profiles" component={ProfilesList} />
        <Route path="/profiles/new" component={NewProfile} />
        <Route path="/profiles/:id" component={EditProfile} />
        <Route path="/sku-catalog" component={SkuCatalogPage} />
        <Route path="/bom-engine" component={BomEngine} />
        <Route path="/bom-output" component={BomOutput} />
        <Route path="/diagnostics/rules-preview" component={RulesPreviewPage} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AuthGuard>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <Router />
          </WouterRouter>
        </AuthGuard>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
