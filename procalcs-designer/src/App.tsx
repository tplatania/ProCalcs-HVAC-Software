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
import RunHistoryPage from "@/pages/diagnostics/run-history";
import RunDiffPage from "@/pages/diagnostics/run-diff";
import EvalBatchPage from "@/pages/diagnostics/eval-batch";
import RegressionSuitesPage from "@/pages/diagnostics/regression-suites";
import ConfidenceTrendPage from "@/pages/diagnostics/confidence-trend";
import SkuBacklogPage from "@/pages/diagnostics/sku-backlog";
import WrightsoftBomPage from "@/pages/diagnostics/wrightsoft-bom";
import WrightsoftBomV2Page from "@/pages/diagnostics/wrightsoft-bom-v2";
import BrowseBomsPage from "@/pages/bom-tool/browse";
import CatalogCoveragePage from "@/pages/diagnostics/catalog-coverage";
import RupInspectPage from "@/pages/diagnostics/rup-inspect";
import DFUnitExplorerPage from "@/pages/diagnostics/dfunit-explorer";
import MappingBrowserPage from "@/pages/diagnostics/mapping-browser";
import PricingImportPage from "@/pages/pricing/import";
import PricingOverridesPage from "@/pages/pricing/overrides";
import PricingConsumablesPage from "@/pages/pricing/consumables";

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
        <Route path="/diagnostics/run-history" component={RunHistoryPage} />
        <Route path="/diagnostics/run-diff" component={RunDiffPage} />
        <Route path="/diagnostics/eval-batch" component={EvalBatchPage} />
        <Route path="/diagnostics/regression-suites" component={RegressionSuitesPage} />
        <Route path="/diagnostics/confidence-trend" component={ConfidenceTrendPage} />
        <Route path="/diagnostics/sku-backlog" component={SkuBacklogPage} />
        <Route path="/diagnostics/wrightsoft-bom" component={WrightsoftBomPage} />
        <Route path="/diagnostics/wrightsoft-bom-v2">{() => <WrightsoftBomV2Page />}</Route>
        {/* Day-28 — BREAD BOM Tool */}
        <Route path="/bom-tool/browse" component={BrowseBomsPage} />
        <Route path="/bom-tool/new">{() => <WrightsoftBomV2Page bread="generate" />}</Route>
        <Route path="/bom-tool/bom/:runId">
          {(params) => <WrightsoftBomV2Page runId={Number(params.runId)} bread="canvas" />}
        </Route>
        <Route path="/diagnostics/catalog-coverage" component={CatalogCoveragePage} />
        <Route path="/diagnostics/rup-inspect" component={RupInspectPage} />
        <Route path="/diagnostics/dfunit-explorer" component={DFUnitExplorerPage} />
        <Route path="/diagnostics/mapping-browser" component={MappingBrowserPage} />
        <Route path="/pricing/import" component={PricingImportPage} />
        <Route path="/pricing/overrides" component={PricingOverridesPage} />
        <Route path="/pricing/consumables" component={PricingConsumablesPage} />
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
