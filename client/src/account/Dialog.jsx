import { useEffect, useId, useRef } from "react";

// A modal built on the native <dialog>: the browser keeps focus inside it,
// Escape closes it, and the page behind can't be clicked.
export default function Dialog({ open, onClose, title, children }) {
  const ref = useRef(null);
  // Each dialog's own id: the page has several (sign-in, account, scoring).
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog__header">
        <h2 id={titleId} className="dialog__title">
          {title}
        </h2>
        <button type="button" className="dialog__close" onClick={onClose}>
          Close
        </button>
      </div>
      {open && children}
    </dialog>
  );
}
