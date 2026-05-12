import { BuilderShell } from "@/components/BuilderShell";
import { PublicLandingPage } from "@/components/PublicLandingPage";

export default function Home() {
  return (
    <>
      <PublicLandingPage />
      <div id="builder">
        <BuilderShell />
      </div>
    </>
  );
}
