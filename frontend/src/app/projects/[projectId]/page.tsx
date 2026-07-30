import { Suspense } from "react";

import { AwaitingState, Bay } from "@/components/console";
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
      {/* The workspace reads its active tab from `?tab=` via useSearchParams (0.14.0),
          which Next 15 requires to sit under a Suspense boundary — without one,
          `next build` fails on the static-generation deopt. This server component is
          the clean streaming edge for it. */}
      <Suspense
        fallback={
          <Bay className="grid min-h-80 place-items-center">
            <AwaitingState variant="loading" label="Loading project" />
          </Bay>
        }
      >
        <ProjectWorkspace projectId={projectId} />
      </Suspense>
    </AppShell>
  );
}
