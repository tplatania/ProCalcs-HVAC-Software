import { useGetClientProfile, useUpdateClientProfile, getGetClientProfileQueryKey, getListClientProfilesQueryKey } from "@/lib/api-hooks";
import { ProfileForm } from "@/components/profile-form";
import { useParams } from "wouter";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";

export default function EditProfile() {
  const params = useParams();
  const id = params.id || "";

  const { data: profile, isLoading } = useGetClientProfile(id, {
    query: { enabled: !!id }
  });
  
  const updateMutation = useUpdateClientProfile();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const handleSubmit = (data: any) => {
    updateMutation.mutate({ id, data }, {
      onSuccess: () => {
        toast({ title: "Profile updated successfully" });
        queryClient.invalidateQueries({ queryKey: getGetClientProfileQueryKey(id) });
        queryClient.invalidateQueries({ queryKey: getListClientProfilesQueryKey() });
      },
      onError: (error: any) => {
        toast({
          title: "Failed to update profile",
          description: error?.error || "An unknown error occurred",
          variant: "destructive"
        });
      }
    });
  };

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex items-center gap-4 py-4 border-b">
          <Skeleton className="h-9 w-9 rounded-md" />
          <Skeleton className="h-8 w-64" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 space-y-8">
            <Skeleton className="h-[400px] w-full rounded-xl" />
            <Skeleton className="h-[300px] w-full rounded-xl" />
          </div>
          <div className="lg:col-span-2 space-y-8">
            <Skeleton className="h-[300px] w-full rounded-xl" />
            <Skeleton className="h-[400px] w-full rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="max-w-6xl mx-auto text-center py-20">
        <h2 className="text-2xl font-bold">Profile not found</h2>
        <p className="text-muted-foreground mt-2">The profile you're looking for doesn't exist or has been deleted.</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
      <ProfileForm 
        initialValues={profile}
        onSubmit={handleSubmit} 
        isSubmitting={updateMutation.isPending} 
      />
    </div>
  );
}
