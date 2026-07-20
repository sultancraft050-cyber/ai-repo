import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function CoolerPage() {
  return (
    <AppChrome>
      <CategoryBrowser category="COOLER" title="CPU Coolers Catalog" />
    </AppChrome>
  );
}
