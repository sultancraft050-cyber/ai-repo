import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function MotherboardPage() {
  return (
    <AppChrome>
      <CategoryBrowser category="MOTHERBOARD" title="Motherboards Catalog" />
    </AppChrome>
  );
}
