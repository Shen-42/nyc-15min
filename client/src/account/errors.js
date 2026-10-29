// Shared with the rest of the site (src/errors.js).
export { errorText } from "../errors";

// Supabase Auth's messages, in the site's words.
export function authMessage(error) {
  const text = error?.message ?? "";
  if (/invalid login credentials/i.test(text)) return "Wrong email or password.";
  if (/email not confirmed/i.test(text)) return "Confirm your email first. Check your inbox for the link.";
  if (/rate limit|too many/i.test(text)) return "Too many emails sent. Try again in an hour.";
  if (/password should be at least/i.test(text)) return "Use at least 8 characters.";
  if (/same.*password|different from the old/i.test(text)) return "Choose a password you haven't used here before.";
  if (/network|fetch/i.test(text)) return "Can't reach the sign-in service. Check your connection.";
  return text || "Something went wrong. Try again.";
}
