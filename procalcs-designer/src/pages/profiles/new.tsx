import { useCreateClientProfile, getListClientProfilesQueryKey, getGetDashboardSummaryQueryKey } from "@/lib/api-hooks";
import { ProfileForm } from "@/components/profile-form";
import { useLocation } from "wouter";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";

export default function NewProfile() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const createMutation = useCreateClientProfile();

  const handleSubmit = (data: any) => {
    createMutation.mutate({ data }, {
      onSuccess: (profile) => {
        toast({ title: "Profile created successfully" });
        queryClient.invalidateQueries({ queryKey: getListClientProfilesQueryKey() });
        queryClient.invalidateQueries({ queryKey: getGetDashboardSummaryQueryKey() });
        setLocation(`/profiles/${profile.id}`);
      },
      onError: (error: any) => {
        toast({
          title: "Failed to create profile",
          description: error?.error || "An unknown error occurred",
          variant: "destructive"
        });
      }
    });
  };

  return (
    <div className="max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
      <ProfileForm 
        onSubmit={handleSubmit} 
        isSubmitting={createMutation.isPending} 
      />
    </div>
  );
}
