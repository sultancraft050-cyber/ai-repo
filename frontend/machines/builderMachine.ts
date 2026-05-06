"use client";

import { assign, fromPromise, setup } from "xstate";
import type {
  BuildPreferences,
  BuildGenerateResponse,
  ComponentKind,
  SelectedComponents,
  ValidationBundle
} from "@/types/builder";
import { selectionKeyByKind } from "@/types/builder";
import { generateBuild, validateAndMeasure } from "@/lib/api";

export type BuilderContext = {
  selected: SelectedComponents;
  preferences: BuildPreferences;
  validation: ValidationBundle | null;
  generatedBuilds: BuildGenerateResponse | null;
  error: string | null;
  buildError: string | null;
  activeKind: ComponentKind;
};

type SelectComponentEvent = {
  type: "SELECT_COMPONENT";
  kind: ComponentKind;
  componentId: string;
};

type BuilderEvent =
  | { type: "START" }
  | { type: "GENERATE_BUILD" }
  | { type: "APPLY_GENERATED_BUILD"; selection: SelectedComponents }
  | SelectComponentEvent
  | { type: "SET_PREFERENCES"; preferences: BuildPreferences }
  | { type: "RETRY" }
  | { type: "RESET" };

const defaultPreferences: BuildPreferences = {
  purpose: "gaming",
  resolution: "1440p",
  region: "US",
  brand_bias: [],
  noise_preference: "balanced",
  upgrade_path_priority: 5
};

function nextStateFor(kind: ComponentKind) {
  if (kind === "CPU") return "selecting_motherboard";
  if (kind === "Motherboard") return "selecting_motherboard";
  return "validating";
}

export const builderMachine = setup({
  types: {} as {
    context: BuilderContext;
    events: BuilderEvent;
  },
  actors: {
    validateWithBackend: fromPromise(
      async ({ input }: { input: { selected: SelectedComponents; preferences: BuildPreferences } }) => {
        return validateAndMeasure(input.selected, input.preferences);
      }
    ),
    generateWithBackend: fromPromise(
      async ({ input }: { input: { preferences: BuildPreferences } }) => {
        return generateBuild(input.preferences);
      }
    )
  },
  guards: {
    backendAccepted: ({ event }) => {
      const output = (event as { output?: ValidationBundle }).output;
      return Boolean(output?.compatibility.valid);
    }
  },
  actions: {
    assignSelection: assign(({ context, event }) => {
      if (event.type !== "SELECT_COMPONENT") return {};
      const key = selectionKeyByKind[event.kind];
      return {
        selected: { ...context.selected, [key]: event.componentId },
        activeKind: event.kind,
        error: null
      };
    }),
    assignFullSelection: assign(({ event }) => {
      if (event.type !== "APPLY_GENERATED_BUILD") return {};
      return {
        selected: event.selection,
        error: null
      };
    }),
    assignPreferences: assign(({ event }) => {
      if (event.type !== "SET_PREFERENCES") return {};
      return { preferences: event.preferences, error: null };
    }),
    assignValidation: assign(({ event }) => {
      const output = (event as { output?: ValidationBundle }).output;
      if (!output) return {};
      return { validation: output, error: null };
    }),
    assignValidationError: assign(({ event }) => ({
      error: String((event as { error?: unknown }).error ?? "Validation failed")
    })),
    assignGeneratedBuilds: assign(({ event }) => {
      const output = (event as { output?: BuildGenerateResponse }).output;
      if (!output) return {};
      return { generatedBuilds: output, buildError: null };
    }),
    assignBuildError: assign(({ event }) => ({
      buildError: String((event as { error?: unknown }).error ?? "Build generation failed")
    })),
    resetContext: assign(() => ({
      selected: {},
      preferences: defaultPreferences,
      validation: null,
      generatedBuilds: null,
      error: null,
      buildError: null,
      activeKind: "CPU" as ComponentKind
    }))
  }
}).createMachine({
  id: "pc-builder-compatibility",
  initial: "idle",
  context: {
    selected: {},
    preferences: defaultPreferences,
    validation: null,
    generatedBuilds: null,
    error: null,
    buildError: null,
    activeKind: "CPU"
  },
  states: {
    idle: {
      on: {
        START: { target: "selecting_cpu" },
        SELECT_COMPONENT: {
          target: "validating",
          actions: "assignSelection"
        },
        SET_PREFERENCES: {
          actions: "assignPreferences"
        },
        GENERATE_BUILD: "generating_build"
      }
    },
    selecting_cpu: {
      on: {
        SELECT_COMPONENT: {
          target: "validating",
          actions: "assignSelection"
        },
        SET_PREFERENCES: { actions: "assignPreferences" },
        GENERATE_BUILD: "generating_build",
        APPLY_GENERATED_BUILD: {
          target: "validating",
          actions: "assignFullSelection"
        },
        RESET: { target: "idle", actions: "resetContext" }
      }
    },
    selecting_motherboard: {
      on: {
        SELECT_COMPONENT: {
          target: "validating",
          actions: "assignSelection"
        },
        SET_PREFERENCES: { actions: "assignPreferences" },
        GENERATE_BUILD: "generating_build",
        APPLY_GENERATED_BUILD: {
          target: "validating",
          actions: "assignFullSelection"
        },
        RESET: { target: "idle", actions: "resetContext" }
      }
    },
    validating: {
      invoke: {
        id: "validateWithBackend",
        src: "validateWithBackend",
        input: ({ context }) => ({
          selected: context.selected,
          preferences: context.preferences
        }),
        onDone: [
          {
            target: "valid_configuration",
            guard: "backendAccepted",
            actions: "assignValidation"
          },
          {
            target: "invalid_configuration",
            actions: "assignValidation"
          }
        ],
        onError: {
          target: "invalid_configuration",
          actions: "assignValidationError"
        }
      }
    },
    valid_configuration: {
      on: {
        GENERATE_BUILD: "generating_build",
        APPLY_GENERATED_BUILD: {
          target: "validating",
          actions: "assignFullSelection"
        },
        SELECT_COMPONENT: {
          target: "validating",
          actions: "assignSelection"
        },
        SET_PREFERENCES: {
          target: "validating",
          actions: "assignPreferences"
        },
        RESET: { target: "idle", actions: "resetContext" }
      }
    },
    invalid_configuration: {
      on: {
        GENERATE_BUILD: "generating_build",
        APPLY_GENERATED_BUILD: {
          target: "validating",
          actions: "assignFullSelection"
        },
        SELECT_COMPONENT: {
          target: "validating",
          actions: "assignSelection"
        },
        SET_PREFERENCES: {
          target: "validating",
          actions: "assignPreferences"
        },
        RETRY: "validating",
        RESET: { target: "idle", actions: "resetContext" }
      }
    },
    generating_build: {
      invoke: {
        id: "generateWithBackend",
        src: "generateWithBackend",
        input: ({ context }) => ({
          preferences: context.preferences
        }),
        onDone: {
          target: "build_generated",
          actions: "assignGeneratedBuilds"
        },
        onError: {
          target: "build_error",
          actions: "assignBuildError"
        }
      }
    },
    build_generated: {
      on: {
        GENERATE_BUILD: "generating_build",
        APPLY_GENERATED_BUILD: {
          target: "validating",
          actions: "assignFullSelection"
        },
        SELECT_COMPONENT: {
          target: "validating",
          actions: "assignSelection"
        },
        SET_PREFERENCES: {
          actions: "assignPreferences"
        },
        RESET: { target: "idle", actions: "resetContext" }
      }
    },
    build_error: {
      on: {
        GENERATE_BUILD: "generating_build",
        APPLY_GENERATED_BUILD: {
          target: "validating",
          actions: "assignFullSelection"
        },
        SET_PREFERENCES: { actions: "assignPreferences" },
        RESET: { target: "idle", actions: "resetContext" }
      }
    }
  }
});
