import { useListClientProfiles, useDeleteClientProfile, getListClientProfilesQueryKey, getGetDashboardSummaryQueryKey } from "@/lib/api-hooks";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, PlusCircle, Building2, Trash2, Edit, FileText, Percent, MoreVertical } from "lucide-react";
import { Link } from "wouter";
import { useState } from "react";
import { format } from "date-fns";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";

export default function ProfilesList() {
  const { data: profiles, isLoading } = useListClientProfiles();
  const [search, setSearch] = useState("");
  const deleteMutation = useDeleteClientProfile();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const filteredProfiles = profiles?.filter(p => 
    p.name.toLowerCase().includes(search.toLowerCase()) || 
    p.supplierName.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = (id: string) => {
    deleteMutation.mutate({ id }, {
      onSuccess: () => {
        toast({ title: "Profile deleted successfully" });
        queryClient.invalidateQueries({ queryKey: getListClientProfilesQueryKey() });
        queryClient.invalidateQueries({ queryKey: getGetDashboardSummaryQueryKey() });
      },
      onError: () => {
        toast({ title: "Failed to delete profile", variant: "destructive" });
      }
    });
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Client Profiles</h1>
          <p className="text-muted-foreground mt-2">
            Manage all client pricing rules, suppliers, and part overrides.
          </p>
        </div>
        <Link href="/profiles/new">
          <Button>
            <PlusCircle className="w-4 h-4 mr-2" />
            New Profile
          </Button>
        </Link>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input 
          placeholder="Search by client or supplier name..." 
          className="pl-10 max-w-md bg-card"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <Card key={i} className="overflow-hidden">
              <div className="h-2 w-full bg-muted" />
              <CardHeader className="pb-4">
                <Skeleton className="h-6 w-3/4 mb-2" />
                <Skeleton className="h-4 w-1/2" />
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredProfiles?.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 border border-dashed rounded-lg bg-card text-center">
          <Building2 className="w-12 h-12 text-muted-foreground mb-4" />
          <h3 className="text-xl font-semibold">No profiles found</h3>
          <p className="text-muted-foreground mt-2 max-w-md">
            {search ? "No profiles match your search criteria. Try adjusting your filters." : "You haven't created any client profiles yet."}
          </p>
          {!search && (
            <Link href="/profiles/new">
              <Button className="mt-6">
                <PlusCircle className="w-4 h-4 mr-2" />
                Create First Profile
              </Button>
            </Link>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredProfiles?.map((profile, index) => (
            <Card key={profile.id} className="flex flex-col overflow-hidden hover-elevate transition-all animate-in fade-in slide-in-from-bottom-4 group" style={{ animationDelay: `${index * 50}ms` }}>
              <div 
                className="h-2 w-full shrink-0 transition-colors" 
                style={{ backgroundColor: profile.brandColor || 'hsl(var(--primary))' }}
              />
              <CardHeader className="pb-4 relative">
                <div className="absolute top-4 right-4">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreVertical className="w-4 h-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <Link href={`/profiles/${profile.id}`}>
                        <DropdownMenuItem className="cursor-pointer">
                          <Edit className="w-4 h-4 mr-2" />
                          Edit Profile
                        </DropdownMenuItem>
                      </Link>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <DropdownMenuItem onSelect={(e) => e.preventDefault()} className="cursor-pointer text-destructive focus:text-destructive">
                            <Trash2 className="w-4 h-4 mr-2" />
                            Delete
                          </DropdownMenuItem>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                            <AlertDialogDescription>
                              This will permanently delete the profile for <strong>{profile.name}</strong>. This action cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction 
                              onClick={() => handleDelete(profile.id)}
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <div className="flex justify-between items-start mb-2 pr-8">
                  <Badge variant={profile.isActive ? "default" : "secondary"} className={profile.isActive ? "bg-green-500/10 text-green-700 hover:bg-green-500/20" : ""}>
                    {profile.isActive ? "Active" : "Inactive"}
                  </Badge>
                </div>
                <CardTitle className="text-xl group-hover:text-primary transition-colors">
                  <Link href={`/profiles/${profile.id}`}>
                    <span className="cursor-pointer">{profile.name}</span>
                  </Link>
                </CardTitle>
                <div className="flex items-center text-sm text-muted-foreground mt-1">
                  <Building2 className="w-3 h-3 mr-1" />
                  {profile.supplierName}
                </div>
              </CardHeader>
              <CardContent className="flex-1 pb-4">
                <div className="grid grid-cols-2 gap-4 bg-muted/30 p-4 rounded-lg border">
                  <div>
                    <div className="flex items-center text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wider">
                      <Percent className="w-3 h-3 mr-1" />
                      Markup
                    </div>
                    <div className="font-semibold">{profile.defaultMarkupPercent}%</div>
                  </div>
                  <div>
                    <div className="flex items-center text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wider">
                      <FileText className="w-3 h-3 mr-1" />
                      Overrides
                    </div>
                    <div className="font-semibold">{profile.partOverrides?.length || 0} Parts</div>
                  </div>
                </div>
              </CardContent>
              <CardFooter className="pt-0 text-xs text-muted-foreground flex justify-between items-center border-t px-6 py-3 bg-muted/10">
                <span>Updated {format(new Date(profile.updatedAt), "MMM d, yyyy")}</span>
                <Link href={`/profiles/${profile.id}`}>
                  <Button variant="ghost" size="sm" className="h-8 text-xs font-medium text-primary hover:bg-primary/10 hover:text-primary">
                    Manage <ArrowRight className="w-3 h-3 ml-1" />
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function ArrowRight(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  )
}
