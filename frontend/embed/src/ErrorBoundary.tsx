"use client";

import { Component, type ReactNode } from "react";

/**
 * The price of running in the host's page instead of a frame: a crash here is
 * a crash in their document. An iframe would have contained it; this has to.
 *
 * Contained to the element, so a bad chat release costs the host a message
 * where the chat was, not their homepage.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override render() {
    if (this.state.failed) {
      return (
        <p style={{ padding: "16px" }}>
          The chat didn&apos;t load. You can reach it at{" "}
          <a href="https://chat.mringdal.com">
            chat.mringdal.com
          </a>
          .
        </p>
      );
    }

    return this.props.children;
  }
}
