import { useEffect, useState } from "react";
import Dialog from "./Dialog";
import Field from "./Field";
import { authMessage } from "./errors";
import { supabase } from "./supabase";

const MIN_PASSWORD = 8;

const TITLES = {
  signIn: "Sign in",
  signUp: "Create an account",
  forgot: "Reset your password",
  newPassword: "Choose a new password",
  checkEmail: "Check your email",
};

// Sign in, create an account, and reset a password (card 13).
// reason: an optional line saying why sign-in is needed ("Sign in to save places").
export default function AuthDialog({ open, onClose, reason, recovering, onRecovered }) {
  const [mode, setMode] = useState("signIn");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState({});
  const [sentTo, setSentTo] = useState(null); // { email, what: "confirm" | "reset" }
  const [busy, setBusy] = useState(false);
  const [unconfirmed, setUnconfirmed] = useState(false);

  // A password-reset link opens the site signed in for recovery: ask for
  // the new password straight away.
  useEffect(() => {
    if (recovering) setMode("newPassword");
  }, [recovering]);

  // Each time the dialog opens, start from "Sign in" with no old errors.
  useEffect(() => {
    if (open && !recovering) {
      setMode("signIn");
      setErrors({});
      setUnconfirmed(false);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  function go(next) {
    setMode(next);
    setErrors({});
    setUnconfirmed(false);
  }

  const redirectTo = window.location.origin;

  async function submit(event) {
    event.preventDefault();
    const found = {};
    if (mode !== "newPassword" && !/^\S+@\S+\.\S+$/.test(email)) found.email = "Enter an email address like name@example.com.";
    if ((mode === "signUp" || mode === "newPassword") && password.length < MIN_PASSWORD)
      found.password = `Use at least ${MIN_PASSWORD} characters.`;
    if (mode === "signIn" && !password) found.password = "Enter your password.";
    setErrors(found);
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      if (mode === "signIn") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          setUnconfirmed(/email not confirmed/i.test(error.message));
          return setErrors({ form: authMessage(error) });
        }
        setPassword("");
        onClose();
      } else if (mode === "signUp") {
        const { data, error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: redirectTo } });
        if (error) return setErrors({ form: authMessage(error) });
        // Signing up with an email that already has an account returns a
        // user with no identities, and no email is sent.
        if (data.user && data.user.identities?.length === 0) {
          return setErrors({ email: "An account with this email already exists. Sign in or reset your password." });
        }
        setPassword("");
        if (data.session) return onClose(); // email confirmation turned off
        setSentTo({ email, what: "confirm" });
        go("checkEmail");
      } else if (mode === "forgot") {
        const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo });
        if (error) return setErrors({ form: authMessage(error) });
        setSentTo({ email, what: "reset" });
        go("checkEmail");
      } else if (mode === "newPassword") {
        const { error } = await supabase.auth.updateUser({ password });
        if (error) return setErrors({ form: authMessage(error) });
        setPassword("");
        onRecovered();
        onClose();
      }
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    const { error } = await supabase.auth.resend({ type: "signup", email, options: { emailRedirectTo: redirectTo } });
    setBusy(false);
    if (error) return setErrors({ form: authMessage(error) });
    setSentTo({ email, what: "confirm" });
    go("checkEmail");
  }

  return (
    <Dialog open={open} onClose={onClose} title={TITLES[mode]}>
      {mode === "checkEmail" ? (
        <div className="dialog__body">
          <p>
            {sentTo?.what === "reset"
              ? `If an account uses ${sentTo.email}, a link to reset the password is on its way.`
              : `We sent a confirmation link to ${sentTo?.email}. Open it to finish signing up.`}
          </p>
          <p className="field__hint">It can take a few minutes. Check your spam folder too.</p>
          <button type="button" className="button button--primary" onClick={() => go("signIn")}>
            Back to sign in
          </button>
        </div>
      ) : (
        <form className="dialog__body" onSubmit={submit} noValidate>
          {reason && mode === "signIn" && <p>{reason}</p>}
          {mode === "newPassword" && <p>Enter a new password for your account.</p>}
          {mode === "forgot" && <p>We'll email you a link to choose a new password.</p>}

          {errors.form && (
            <p className="message message--error" role="alert">
              {errors.form}
            </p>
          )}
          {unconfirmed && (
            <button type="button" className="button button--link" onClick={resend} disabled={busy}>
              Send the confirmation email again
            </button>
          )}

          {mode !== "newPassword" && (
            <Field
              id="auth-email"
              label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value.trim())}
              error={errors.email}
              autoFocus
            />
          )}
          {mode !== "forgot" && (
            <Field
              id="auth-password"
              label={mode === "newPassword" ? "New password" : "Password"}
              type="password"
              autoComplete={mode === "signIn" ? "current-password" : "new-password"}
              hint={mode === "signIn" ? undefined : `At least ${MIN_PASSWORD} characters.`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              autoFocus={mode === "newPassword"}
            />
          )}

          <button type="submit" className="button button--primary" disabled={busy}>
            {busy ? "Please wait…" : { signIn: "Sign in", signUp: "Create account", forgot: "Send reset link", newPassword: "Save password" }[mode]}
          </button>

          {mode === "signIn" && (
            <div className="dialog__links">
              <button type="button" className="button button--link" onClick={() => go("forgot")}>
                Forgot your password?
              </button>
              <button type="button" className="button button--link" onClick={() => go("signUp")}>
                Create an account
              </button>
            </div>
          )}
          {(mode === "signUp" || mode === "forgot") && (
            <button type="button" className="button button--link" onClick={() => go("signIn")}>
              Back to sign in
            </button>
          )}
        </form>
      )}
    </Dialog>
  );
}
