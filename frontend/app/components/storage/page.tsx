import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function StoragePage() {
  return (
    <AppChrome>
      <CategoryBrowser category="STORAGE" title="Storage Catalog" />
    </AppChrome>
  );
}
