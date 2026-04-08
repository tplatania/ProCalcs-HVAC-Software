import { useGetDashboardSummary } from "@/lib/api-hooks";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Users, CheckCircle2, XCircle, FileText, Building2, TrendingUp, ArrowRight, PlusCircle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Link } from "wouter";
import { format } from "date-fns";

export default function Dashboard() {
  const { data: summary, isLoading } = useGetDashboardSummary();

  const stats = summary ? [
    {
      title: "Total Profiles",
      value: summary.totalProfiles,
      icon: Users,
      color: "text-blue-500",
      bg: "bg-blue-500/10"
    },
    {
      title: "Active Profiles",
      value: summary.activeProfiles,
      icon: CheckCircle2,
      color: "text-green-500",
      bg: "bg-green-500/10"
    },
    {
      title: "Inactive Profiles",
      value: summary.inactiveProfiles,
      icon: XCircle,
      color: "text-gray-500",
      bg: "bg-gray-500/10"
    },
    {
      title: "Part Overrides",
      value: summary.totalPartOverrides,
      icon: FileText,
      color: "text-purple-500",
      bg: "bg-purple-500/10"
    },
    {
      title: "Suppliers",
      value: summary.suppliersCount,
      icon: Building2,
      color: "text-orange-500",
      bg: "bg-orange-500/10"
    }
  ] : [];

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard Overview</h1>
        <p className="text-muted-foreground mt-2">
          Monitor your client profiles, markup rules, and active part overrides.
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map(i => (
            <Card key={i}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-8 w-8 rounded-full" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-12" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {stats.map((stat, index) => (
            <Card key={stat.title} className="hover-elevate transition-all animate-in fade-in slide-in-from-bottom-4" style={{ animationDelay: `${index * 100}ms` }}>
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">{stat.title}</CardTitle>
                <div className={`w-8 h-8 rounded-md flex items-center justify-center ${stat.bg}`}>
                  <stat.icon className={`w-4 h-4 ${stat.color}`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <Card className="lg:col-span-2 flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Recent Profiles</CardTitle>
                <CardDescription>Latest client profiles modified or created.</CardDescription>
              </div>
              <Link href="/profiles">
                <span className="text-sm font-medium text-primary hover:underline flex items-center gap-1 cursor-pointer">
                  View All <ArrowRight className="w-4 h-4" />
                </span>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="flex-1">
            {isLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : summary?.recentProfiles.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 border border-dashed rounded-lg bg-muted/20">
                <Users className="w-10 h-10 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold">No profiles yet</h3>
                <p className="text-sm text-muted-foreground mt-1 mb-4">Get started by creating your first client profile.</p>
                <Link href="/profiles/new" className="text-sm font-medium bg-primary text-primary-foreground px-4 py-2 rounded-md hover:bg-primary/90 transition-colors">
                  Create Profile
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                {summary?.recentProfiles.map(profile => (
                  <Link key={profile.id} href={`/profiles/${profile.id}`}>
                    <div className="flex items-center justify-between p-4 rounded-lg border bg-card hover:bg-muted/50 transition-colors cursor-pointer group">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded bg-primary/10 flex items-center justify-center text-primary font-bold">
                          {profile.name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-foreground group-hover:text-primary transition-colors">{profile.name}</p>
                          <p className="text-xs text-muted-foreground flex items-center gap-2">
                            <span>{profile.supplierName}</span>
                            <span className="w-1 h-1 rounded-full bg-border" />
                            <span>Updated {format(new Date(profile.updatedAt), "MMM d, yyyy")}</span>
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <div className="flex flex-col items-end">
                          <span className="font-medium">{profile.defaultMarkupPercent}%</span>
                          <span className="text-xs text-muted-foreground">Markup</span>
                        </div>
                        <div className="flex flex-col items-end">
                          <span className="font-medium">{profile.partOverrides?.length || 0}</span>
                          <span className="text-xs text-muted-foreground">Overrides</span>
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
            <CardDescription>BOM Engine Status</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="text-sm font-medium">API Connectivity</span>
                </div>
                <span className="text-sm text-muted-foreground">Online</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="text-sm font-medium">Database Sync</span>
                </div>
                <span className="text-sm text-muted-foreground">12ms</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="text-sm font-medium">Pricing Engine</span>
                </div>
                <span className="text-sm text-muted-foreground">Active</span>
              </div>
              
              <div className="pt-6 border-t">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">Quick Actions</h4>
                <div className="space-y-2">
                  <Link href="/profiles/new">
                    <Button variant="outline" className="w-full justify-start text-sm">
                      <PlusCircle className="w-4 h-4 mr-2" />
                      Create New Profile
                    </Button>
                  </Link>
                  <Link href="/profiles">
                    <Button variant="outline" className="w-full justify-start text-sm">
                      <Users className="w-4 h-4 mr-2" />
                      Manage All Profiles
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
