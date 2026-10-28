import { useState } from "react";
import { errorText } from "./errors";

// "Save this spot", next to the score it saves (card 13). Signed out, it
// asks to sign in first.
export default function SaveSpot({ point, account, onNeedSignIn, onSaved }) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(null);
  const [busy, setBusy] = useState(false);

  if (saved && saved.point === point) {
    return (
      <p className="save-spot__done" role="status">
        Saved as “{saved.name}”.
      </p>
    );
  }

  if (!naming) {
    return (
      <button
        type="button"
        className="button save-spot"
        onClick={() => (account.session ? setNaming(true) : onNeedSignIn("Sign in to save places."))}
      >
        Save this spot
      </button>
    );
  }

  async function submit(event) {
    event.preventDefault();
    const clean = name.trim();
    if (!clean) return setError("Give the place a name.");
    setBusy(true);
    try {
      const res = await account.authFetch("/api/saved-places", {
        method: "POST",
        body: JSON.stringify({ name: clean, lat: point[0], lng: point[1] }),
      });
      if (!res.ok) return setError(await errorText(res));
      const place = await res.json();
      setSaved({ name: place.name, point });
      setNaming(false);
      setName("");
      setError(null);
      onSaved(place);
    } catch {
      setError("Couldn't reach the server. Try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="save-spot__form" onSubmit={submit} noValidate>
      <label htmlFor="save-name" className="field__label">
        Name this spot
      </label>
      <div className="save-spot__row">
        <input
          id="save-name"
          className="field__input"
          value={name}
          maxLength={60}
          autoComplete="off"
          placeholder="Home, Work, Mom's place"
          onChange={(e) => setName(e.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "save-name-error" : undefined}
          autoFocus
        />
        <button type="submit" className="button button--primary" disabled={busy}>
          Save
        </button>
        <button type="button" className="button" onClick={() => setNaming(false)}>
          Cancel
        </button>
      </div>
      {error && (
        <p id="save-name-error" className="field__error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
