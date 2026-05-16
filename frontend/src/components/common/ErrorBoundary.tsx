import { Component, type ReactNode } from "react";
import { Spinner } from "./Spinner";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="error-boundary-fallback">
          <h3>页面加载出错</h3>
          <p>{this.state.error?.message || "未知错误"}</p>
          <button type="button" onClick={this.handleReset}>重试</button>
        </div>
      );
    }
    return this.props.children;
  }
}
