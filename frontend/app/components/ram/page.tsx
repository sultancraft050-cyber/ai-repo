import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function RamPage() {
  return (
    <AppChrome>
      <CategoryBrowser category="RAM" title="Memory (RAM) Catalog" />
    </AppChrome>
  );
}
