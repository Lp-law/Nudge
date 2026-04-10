import { useCallback, useRef, useState } from "react";
import { ActionType, runAction } from "../api/ai";

export interface AIActionState {
  isLoading: boolean;
  result: string | null;
  error: string | null;
}

export interface AIActionHook extends AIActionState {
  execute: (action: ActionType, text: string) => Promise<void>;
  reset: () => void;
}

/**
 * Hook that wraps a backend AI action call with loading / error / result state.
 */
export function useAIAction(): AIActionHook {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);

  const execute = useCallback(
    async (action: ActionType, text: string) => {
      abortRef.current = false;
      setIsLoading(true);
      setResult(null);
      setError(null);

      try {
        const res = await runAction(action, text);
        if (!abortRef.current) {
          setResult(res);
        }
      } catch (err: unknown) {
        if (!abortRef.current) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!abortRef.current) {
          setIsLoading(false);
        }
      }
    },
    [],
  );

  const reset = useCallback(() => {
    abortRef.current = true;
    setIsLoading(false);
    setResult(null);
    setError(null);
  }, []);

  return { isLoading, result, error, execute, reset };
}
