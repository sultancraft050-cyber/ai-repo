import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function CpuPage() {
  return (
    <AppChrome>
      <CategoryBrowser category="CPU" title="CPUs Catalog" />
    </AppChrome>
  );
}
