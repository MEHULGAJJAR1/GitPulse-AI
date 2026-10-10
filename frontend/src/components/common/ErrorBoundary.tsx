import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  failed: boolean;
}

/**
 * Last-resort boundary: a render error shows a recoverable panel instead of a blank page.
 * Only the error name and a generic message are logged; no request data or keys are included.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, _info: ErrorInfo): void {
    console.error(`[gitpulse] render error: ${error.name}`);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="grid min-h-dvh place-items-center p-6" role="alert">
        <div className="max-w-md rounded-2xl border border-white/10 bg-ink-900/70 p-6 text-center">
          <p className="text-lg font-semibold text-slate-100">Something went wrong while rendering this page.</p>
          <p className="mt-2 text-sm text-slate-400">Your data is unchanged. Reload to try again.</p>
          <button
            type="button"
            className="mt-4 rounded-xl border border-white/15 px-4 py-2 text-sm text-slate-200 hover:bg-white/5"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
