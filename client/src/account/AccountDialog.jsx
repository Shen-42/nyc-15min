import { useState } from "react";
import AdminPanel from "./AdminPanel";
import Dialog from "./Dialog";
import { errorText } from "./errors";

// The signed-in person's account (card 13): sign out, the admin panel for
// admins, and deleting the account. Deleting takes a second step, where
// "Keep account" is the default and has the focus.
export default function AccountDialog({ open, onClose, account, savedCount, onDeleted }) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function close() {
    setConfirming(false);
    setError(null);
    onClose();
  }

  async function deleteAccount() {
    setBusy(true);
    setError(null);
    try {
      const res = await account.authFetch("/api/account", { method: "DELETE" });
      if (!res.ok) return setError(await errorText(res));
      await account.signOut();
      onDeleted();
      close();
    } catch {
      setError("Couldn't reach the server. Try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Account">
      <div className="dialog__body">
        <p>
          Signed in as <strong>{account.user?.email ?? account.session?.user?.email}</strong>
          {account.user?.role === "admin" && " (admin)"}
        </p>
        <button
          type="button"
          className="button"
          onClick={() => {
            account.signOut();
            close();
          }}
        >
          Sign out
        </button>

        {account.user?.role === "admin" && <AdminPanel authFetch={account.authFetch} />}

        {/* Set apart from everything else, so it isn't pressed by mistake. */}
        <section className="account__section account__danger" aria-labelledby="delete-title">
          <h3 id="delete-title" className="account__heading">
            Delete account
          </h3>
          {!confirming ? (
            <>
              <p className="field__hint">Removes your sign-in, saved places, and saved needs.</p>
              <button type="button" className="button button--danger" onClick={() => setConfirming(true)}>
                Delete account…
              </button>
            </>
          ) : (
            <>
              <p role="alert">
                Delete your account and {savedCount === 1 ? "1 saved place" : `${savedCount} saved places`}? This can't
                be undone.
              </p>
              {error && <p className="message message--error">{error}</p>}
              <div className="account__actions">
                <button type="button" className="button" onClick={() => setConfirming(false)} autoFocus>
                  Keep account
                </button>
                <button type="button" className="button button--danger" onClick={deleteAccount} disabled={busy}>
                  {busy ? "Deleting…" : "Delete account"}
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </Dialog>
  );
}
