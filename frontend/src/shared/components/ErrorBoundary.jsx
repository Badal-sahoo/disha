/**
 * Catches the "TODO ..." errors thrown by unimplemented feature stubs so one
 * unfinished panel cannot blank the whole dashboard. Fully implemented.
 *
 * PROPS: label = str, children = ReactNode
 */
import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="stub-notice">
          <strong>{this.props.label ?? "Not built yet"}</strong>
          <code>{this.state.error.message}</code>
        </div>
      );
    }
    return this.props.children;
  }
}
