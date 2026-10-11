import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an unhandled error:", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[350px] w-full flex-col items-center justify-center p-8 text-center bg-white rounded-2xl border border-neutral-200 shadow-sm">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50 text-amber-600 mb-4 border border-amber-200">
            <AlertTriangle size={24} />
          </div>
          <h2 className="text-base font-semibold text-neutral-900 mb-1">
            {this.props.fallbackTitle || "Something went wrong in this view"}
          </h2>
          <p className="text-xs text-neutral-500 max-w-md mb-6 leading-relaxed">
            An unexpected error occurred while displaying this content. Your data and session are intact.
            {this.state.error?.message ? ` (${this.state.error.message})` : ""}
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={this.handleReset}
              className="px-4 py-2 text-xs font-medium text-neutral-700 bg-neutral-100 hover:bg-neutral-200 rounded-lg transition-colors"
            >
              Try again
            </button>
            <button
              onClick={this.handleReload}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-neutral-900 bg-[#FBC648] hover:bg-[#F0BD44] rounded-lg transition-colors shadow-sm"
            >
              <RefreshCw size={13} />
              Reload application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
