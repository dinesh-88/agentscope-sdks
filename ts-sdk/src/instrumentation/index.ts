import { instrumentFetch } from "./fetch";

let restoreInstrumentation: (() => void) | null = null;

export function autoTrace(providers?: string[]): void {
  if (restoreInstrumentation) {
    return;
  }
  restoreInstrumentation = instrumentFetch({ providers });
}

export function autoInstrument(providers?: string[]): void {
  autoTrace(providers);
}

export function resetAutoInstrumentation(): void {
  if (!restoreInstrumentation) {
    return;
  }
  restoreInstrumentation();
  restoreInstrumentation = null;
}

export { instrumentFetch };
