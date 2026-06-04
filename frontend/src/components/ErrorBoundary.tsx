import { Component, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useLocale } from "../lib/useLocale";

type InnerProps = {
  children: ReactNode;
  title: string;
  retryLabel: string;
};

type State = { hasError: boolean };

/**
 * Catches render-time errors in the page subtree so one broken page shows a
 * recoverable fallback instead of blanking the whole dashboard.
 */
class ErrorBoundaryInner extends Component<InnerProps, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: unknown) {
    // Surface for debugging; a monitoring hook could report here.
    console.error("[Plugo] Page render error:", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-12 text-center">
        <AlertTriangle className="h-10 w-10 text-amber-500" />
        <p className="text-gray-700">{this.props.title}</p>
        <button
          type="button"
          onClick={() => this.setState({ hasError: false })}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          {this.props.retryLabel}
        </button>
      </div>
    );
  }
}

/**
 * Functional wrapper: pulls localized strings and keys the boundary on the
 * route path so navigating to another page automatically clears a prior error.
 */
export default function ErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { t } = useLocale();
  return (
    <ErrorBoundaryInner
      key={location.pathname}
      title={t("common.errorTitle")}
      retryLabel={t("common.errorRetry")}
    >
      {children}
    </ErrorBoundaryInner>
  );
}
