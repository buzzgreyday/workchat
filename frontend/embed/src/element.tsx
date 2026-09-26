import { createRoot, type Root } from "react-dom/client";

import { ErrorBoundary } from "./ErrorBoundary";
// workchat's own chat, unchanged, and the only component this reaches for.
// Everything else in this folder exists to put it in a custom element.
import Chat from "../../src/components/chat/Chat";
import { setApiUrl } from "../../src/lib/api";
import { DEFAULT_OWNER } from "../../src/lib/owner-defaults";
import type { ChatOwner } from "../../src/components/chat/ChatProvider";
// Compiled by `build.mjs`, arriving here as text. See `embed.css`.
import chatCss from "./embed.css";

/**
 * <workchat-chat> — the chat, as an element any page can use.
 *
 * Public API, versioned like one:
 *
 *   Attributes   api-url, about, claim, owner-name, header
 *   Events       workchat-usage (detail: { used, remaining, max })
 *   CSS          the --chat-* palette and fonts, set on the element by the
 *                host page
 *
 * No close event: in the host's own document Escape reaches their <dialog>
 * by itself. Forwarding it was an iframe problem.
 *
 * Adding to any of the three is safe. Renaming or removing is a breaking
 * change for every page that embeds this, and there is no version pin to
 * protect them — that is the trade for decoupled deploys.
 */
const ATTRIBUTES = [
  "api-url",
  "about",
  "claim",
  "owner-name",
  "header",
  // `owner-github` and `owner-linkedin` were here. Their links moved out of
  // the chat onto the standalone page, so a host page that still sets them
  // gets what it would have got from any unknown attribute: nothing, and no
  // error.
] as const;

/**
 * One sheet for the page, not one per element.
 *
 * Constructed stylesheets exist to be shared: the CSS is parsed once however
 * many chats a page mounts, and the same object can be adopted by every shadow
 * root. Built lazily so the parse happens on first use rather than on load.
 */
let sheet: CSSStyleSheet | null = null;

function stylesheet(): CSSStyleSheet {
  if (!sheet) {
    sheet = new CSSStyleSheet();
    sheet.replaceSync(chatCss);
  }

  return sheet;
}

class WorkchatChat extends HTMLElement {
  static observedAttributes = ATTRIBUTES;

  #shadow: ShadowRoot | null = null;
  #mount: HTMLDivElement | null = null;
  #root: Root | null = null;

  connectedCallback() {
    // Built once and kept for the life of the element. `attachShadow` throws
    // on an element that already hosts a shadow tree, so a disconnect must not
    // discard this even though it discards the React root — an element that is
    // removed and put back is ordinary, and it used to be fatal.
    if (!this.#shadow) {
      // Open, not closed: a closed root would stop the host from styling or
      // inspecting anything, and the isolation that matters here is CSS, which
      // an open root gives all the same.
      this.#shadow = this.attachShadow({
        mode: "open",
      });

      // Adopted rather than injected as a <style> tag: the sheet is parsed
      // once and shared, and it lands inside the shadow root, so the host
      // page's stylesheet stays untouched in both directions.
      this.#shadow.adoptedStyleSheets = [
        stylesheet(),
      ];

      this.#mount =
        document.createElement("div");
      this.#mount.style.height = "100%";
      this.#shadow.append(this.#mount);
    }

    // Absent after a real removal, still there after a move. `createRoot` on a
    // container that has been unmounted is fine; on one that has not is the
    // "container is already a root" warning, which is why the unmount below
    // and this have to agree about which just happened.
    if (!this.#root && this.#mount) {
      this.#root = createRoot(this.#mount);
    }

    this.#render();
  }

  disconnectedCallback() {
    // Unmounted in a microtask: React throws if a root is unmounted while it
    // is rendering, and a move in the DOM is a disconnect immediately
    // followed by a connect. By the time this runs, a move has already
    // reconnected and there is nothing to tear down.
    queueMicrotask(() => {
      if (this.isConnected) {
        return;
      }

      this.#root?.unmount();
      this.#root = null;
    });
  }

  attributeChangedCallback() {
    this.#render();
  }

  #render() {
    // Module state, not a prop: the services read it when they send, and they
    // are reached through hooks rather than through anything this can pass.
    // Set before the render that will trigger the first request.
    setApiUrl(
      this.getAttribute("api-url") ?? "/api",
    );

    // Custom properties inherit through the shadow boundary, and a rule the
    // host page writes for this element outranks the `:host` defaults inside
    // it. So the palette is themeable with nothing passed and no protocol to
    // keep in sync — theming is the one thing this needed no code for.
    this.#root?.render(
      <ErrorBoundary>
        <Chat
          claim={
            this.getAttribute("claim") ??
            undefined
          }
          owner={this.#owner()}
          // Read on the first render only, which is the one that happens in
          // `connectedCallback` — React sets a custom element's attributes
          // before it appends it, so the seed is here in time.
          seedQuestion={
            this.getAttribute("about") ?? undefined
          }
          // This is a component of the host's page, not the page. Without it
          // the chat measures the visual viewport and writes `--app-height`
          // onto the host's own <html> — a document it does not own, for a
          // rule that only exists outside this shadow root.
          ownsViewport={false}
          // `header="none"` for a host with a header of its own. Any other
          // value, or none, keeps it — the default a page that says nothing
          // has always had.
          showHeader={
            this.getAttribute("header") !== "none"
          }
          onUsageChange={(usage) =>
            this.#emit("workchat-usage", usage)
          }
        />
      </ErrorBoundary>,
    );
  }

  /**
   * Whose CV this is.
   *
   * The app reads this from the environment on the server and hands it down;
   * an embed has no server render of its own, so the host page's attributes
   * are the only channel. Only the name: the GitHub and LinkedIn links live
   * on the standalone page now, outside the chat, and a host page has its
   * own way of linking to its owner.
   */
  #owner(): ChatOwner {
    return {
      name:
        this.getAttribute("owner-name") ??
        DEFAULT_OWNER.name,
    };
  }

  #emit(type: string, detail?: unknown) {
    // composed, so the event crosses the shadow boundary and the host can
    // listen on the element rather than on something inside it.
    this.dispatchEvent(
      new CustomEvent(type, {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

// Guarded: the script may be loaded twice on a page that mounts the chat in
// two places, and registering a name twice throws.
if (!customElements.get("workchat-chat")) {
  customElements.define(
    "workchat-chat",
    WorkchatChat,
  );
}

export {};
