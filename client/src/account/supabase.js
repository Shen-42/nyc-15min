import { createClient } from "@supabase/supabase-js";

// Sign-in (card 13). The browser only uses Supabase to sign people in; saved
// places and profiles go through our API, which checks the sign-in itself.
// The publishable key is meant to be public: on its own it can't read or
// write any table (row-level security, supabase/schema.sql).
// Without these settings (client/.env.local, or the site's Environment page
// on Render) the site works as before, with no sign-in.
// Only the project's address is wanted (https://<project>.supabase.co). The
// dashboard also shows it with /rest/v1 on the end; that would break sign-in,
// so anything after the host is dropped.
const url = import.meta.env.VITE_SUPABASE_URL?.match(/^https?:\/\/[^/]+/)?.[0];
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const supabase = url && key ? createClient(url, key) : null;
