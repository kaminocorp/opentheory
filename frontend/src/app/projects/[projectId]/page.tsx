import { ProjectDetail } from "@/components/projects/project-detail";
import { SiteHeader } from "@/components/shell/site-header";

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
        <ProjectDetail projectId={projectId} />
      </section>
    </main>
  );
}
