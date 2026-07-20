import { AppChrome } from "@/components/AppChrome";
import { Award, ShieldAlert, ExternalLink } from "lucide-react";

export default function AttributionPage() {
  return (
    <AppChrome>
      <main className="p-6 max-w-4xl mx-auto">
        <h1 className="text-3xl font-extrabold text-ink tracking-tight flex items-center gap-2 mb-3">
          <Award className="text-signal" size={28} />
          Data Sources & Attribution
        </h1>
        <p className="text-sm text-muted mb-8">
          SaudiBuild respects intellectual property, open-source compliance, and attribution requirements. Below is the documentation of public database sources used in this platform.
        </p>

        <div className="bg-[#0b1220]/60 border border-line rounded-2xl p-6 mb-8">
          <h2 className="text-lg font-bold text-ink mb-3 flex items-center gap-2">
            BuildCores OpenDB
          </h2>
          <p className="text-sm text-muted leading-relaxed mb-4">
            Component specifications and technical features used in the Catalog V2 section are derived from the{" "}
            <a
              href="https://github.com/buildcores/buildcores-open-db"
              target="_blank"
              rel="noopener noreferrer"
              className="text-signal hover:underline inline-flex items-center gap-0.5"
            >
              BuildCores OpenDB <ExternalLink size={12} />
            </a>
            .
          </p>

          <div className="bg-panel border border-line rounded-xl p-4 mb-4 text-xs text-muted leading-relaxed">
            <span className="font-extrabold text-ink block mb-1">License & Terms:</span>
            This database is made available under the Open Data Commons Attribution License (ODC-By) v1.0. 
            You are free to share, copy, distribute, modify, and produce works from this database as long as attribution is maintained.
          </div>

          <div className="flex gap-4">
            <a
              href="https://opendatacommons.org/licenses/by/1-0/"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-panel border border-line hover:border-signal/40 text-ink rounded-lg text-xs font-bold transition-all inline-flex items-center gap-1.5"
            >
              ODC-By 1.0 License Text <ExternalLink size={12} />
            </a>
            <a
              href="https://github.com/buildcores/buildcores-open-db"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-[#0d1527] border border-line hover:border-signal/40 text-ink rounded-lg text-xs font-bold transition-all inline-flex items-center gap-1.5"
            >
              Source Repository <ExternalLink size={12} />
            </a>
          </div>
        </div>

        <div className="bg-[#0b1220]/60 border border-line rounded-2xl p-6">
          <h2 className="text-lg font-bold text-ink mb-3 flex items-center gap-2">
            <ShieldAlert className="text-amber-500" size={19} />
            Disclaimer & Media Rights
          </h2>
          <p className="text-sm text-muted leading-relaxed mb-4">
            This platform is an independent community project. It is not affiliated with, endorsed by, or associated with BuildCores in any manner.
          </p>
          <p className="text-sm text-muted leading-relaxed">
            The database license does not grant rights to separate images, 3D assets, trademarks, or other independently protected branding or media assets. Consequently, no images, media files, or 3D models were copied or imported in this process.
          </p>
        </div>
      </main>
    </AppChrome>
  );
}
