/**
 * Stops one broken panel from blanking the whole dashboard.
 *
 * React unmounts the entire tree when a render throws, so without this a single
 * bad API shape shows the operator a white screen instead of the eight panels
 * that are still working.
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
          <strong>{this.props.label ?? "This panel failed"}</strong>
          <code>{this.state.error.message}</code>
        </div>
      );
    }
    return this.props.children;
  }
}
