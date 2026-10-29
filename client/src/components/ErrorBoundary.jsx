import { Component, useEffect, useRef } from "react";

const FALLBACK = {
  map: {
    title: "The map stopped working",
    text: "Your settings are saved. Reload the page to start the map again.",
  },
  panel: {
    title: "The panel stopped working",
    text: "Your settings are saved. Reload the page to start again.",
  },
  app: {
    title: "Something went wrong",
    text: "Reload the page to start again.",
  },
};

// Catches a crash in part of the page (card 14), so it shows a message with
// a Reload button instead of going blank. The map and the panel each have
// one, so a crash in one leaves the other working; a last one wraps the app.
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error(`The ${this.props.name} crashed:`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <Fallback name={this.props.name} className={this.props.className} />;
  }
}

function Fallback({ name, className = "" }) {
  const button = useRef(null);
  const { title, text } = FALLBACK[name] ?? FALLBACK.app;

  // Move focus to the way out, so keyboard and screen reader users land on it.
  useEffect(() => button.current?.focus(), []);

  return (
    <div className={`crash ${className}`} role="alert">
      <h2 className="crash__title">{title}</h2>
      <p>{text}</p>
      <button ref={button} type="button" className="button button--primary" onClick={() => window.location.reload()}>
        Reload the page
      </button>
    </div>
  );
}
