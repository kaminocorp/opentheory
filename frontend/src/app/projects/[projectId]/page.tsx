import { AppShell } from "@/components/shell/app-shell";
import { ProjectWorkspace } from "@/components/workspace/project-workspace";

type ProjectPageProps = {
  params: Promise<{
    projectId: string;
  }>;
};

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { projectId } = await params;

  return (
    <AppShell>
      <ProjectWorkspace projectId={projectId} />
    </AppShell>
  );
}
