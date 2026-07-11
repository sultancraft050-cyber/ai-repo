export function compareReleaseContracts(frontendRelease, backendRelease) {
  if (!frontendRelease || !backendRelease) {
    return { status: "unverifiable", detail: "release metadata unavailable" };
  }
  const required = ["service", "release", "api_contract_version"];
  if ([frontendRelease, backendRelease].some((release) => required.some((field) => !release[field]))) {
    return { status: "unverifiable", detail: "required release fields are unknown" };
  }
  if (frontendRelease.api_contract_version !== backendRelease.api_contract_version) {
    return {
      status: "incompatible",
      detail: `API contract ${frontendRelease.api_contract_version} != ${backendRelease.api_contract_version}`,
    };
  }
  return {
    status: "compatible",
    detail: `API contract ${frontendRelease.api_contract_version}; deployment releases may differ`,
  };
}
