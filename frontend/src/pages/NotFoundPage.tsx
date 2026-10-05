import { PageHeader } from "../layout/PageHeader";
import { NotFoundState } from "../components/states";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" />
      <NotFoundState what="page" backTo="/overview" backLabel="Back to Overview" />
    </>
  );
}
