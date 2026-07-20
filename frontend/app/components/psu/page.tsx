import { AppChrome } from "@/components/AppChrome";
import { CategoryBrowser } from "@/components/CategoryBrowser";

export default function PsuPage() {
  return (
    <AppChrome>
      <CategoryBrowser category="PSU" title="Power Supply Units (PSU) Catalog" />
    </AppChrome>
  );
}
