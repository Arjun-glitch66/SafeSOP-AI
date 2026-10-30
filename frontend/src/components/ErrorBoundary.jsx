import { Component } from "react";
import { AlertTriangle } from "lucide-react";

// Keeps a crash in one view from blanking the whole app. App.jsx keys it by page,
// so navigating to another view resets it.
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("View crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="notice-banner" role="alert">
        <AlertTriangle size={20} />
        <div>
          <strong>This view hit an unexpected error</strong>
          <p>{this.state.error.message}. Your saved documents and versions are not affected. Open another view or reload the page.</p>
        </div>
      </div>
    );
  }
}
