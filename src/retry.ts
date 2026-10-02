export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  if (typeof err === "string" && err.trim()) {
    return err;
  }
  return fallback;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Retry a backend call that throws. Failures that return ``{ok:false}`` are not retried here. */
export async function withRetry<T>(run: () => Promise<T>, attempts = 3): Promise<T> {
  let last: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await run();
    } catch (err) {
      last = err;
      if (attempt + 1 < attempts) {
        await sleep(400 * (attempt + 1));
      }
    }
  }
  throw last;
}
