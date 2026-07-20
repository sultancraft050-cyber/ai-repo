import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function GpuPage() {
  return (
    <AppChrome>
      <CategoryBrowser category="GPU" title="GPUs Catalog" />
    </AppChrome>
  );
}
