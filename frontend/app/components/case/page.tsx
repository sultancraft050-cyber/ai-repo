import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function CasePage() {
  return (
    <AppChrome>
      <CategoryBrowser category="CASE" title="PC Cases Catalog" />
    </AppChrome>
  );
}
