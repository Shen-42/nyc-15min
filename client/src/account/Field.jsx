// A labeled input with its error right under it. The error is tied to the
// input (aria-describedby) and announced when it appears (role="alert").
export default function Field({ id, label, error, hint, ...input }) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="field__hint">
          {hint}
        </p>
      )}
      <input id={id} className="field__input" aria-invalid={Boolean(error)} aria-describedby={describedBy} {...input} />
      {error && (
        <p id={`${id}-error`} className="field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
