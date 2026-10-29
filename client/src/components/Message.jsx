import { useEffect, useRef } from "react";

// Every message in the panel (card 14): one style, one place. Errors are
// announced at once (role="alert"); other messages politely (role="status").
// With onRetry, the message has its own "Try again" button, and keyboard
// focus moves to it when the message appears.
export default function Message({ kind = "warn", text, onRetry }) {
  const button = useRef(null);

  useEffect(() => {
    if (onRetry) button.current?.focus();
  }, [text]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={`message message--${kind}`} role={kind === "error" ? "alert" : "status"}>
      <p>{text}</p>
      {onRetry && (
        <button ref={button} type="button" className="button message__retry" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
