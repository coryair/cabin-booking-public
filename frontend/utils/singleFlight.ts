export function createSingleFlightTask<T>(task: () => Promise<T>): () => Promise<T> {
  let pending: Promise<T> | null = null;

  return () => {
    if (!pending) {
      pending = task();
    }
    return pending;
  };
}
