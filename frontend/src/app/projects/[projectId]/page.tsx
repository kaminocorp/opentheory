import { SiteHeader } from "@/components/shell/site-header";
import { ProjectWorkspace } from "@/components/workspace/project-workspace";

type ProjectPageProps = {
  params: Promise<{
    projectId: string;
  }>;
};

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { projectId } = await params;

  return (
    <main className="min-h-screen">
      <SiteHeader />
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <ProjectWorkspace projectId={projectId} />
      </section>
    </main>
  );
}
