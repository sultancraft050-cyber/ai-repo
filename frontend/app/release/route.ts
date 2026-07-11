import { NextResponse } from "next/server";

const API_CONTRACT_VERSION = process.env.NEXT_PUBLIC_API_CONTRACT_VERSION ?? "1";

export function GET() {
  return NextResponse.json({
    service: "frontend",
    environment: process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "unknown",
    release: process.env.NEXT_PUBLIC_APP_VERSION ?? "unknown",
    git_sha: process.env.NEXT_PUBLIC_GIT_SHA ?? process.env.VERCEL_GIT_COMMIT_SHA ?? null,
    build_time: process.env.NEXT_PUBLIC_BUILD_TIME ?? null,
    api_contract_version: API_CONTRACT_VERSION
  });
}
