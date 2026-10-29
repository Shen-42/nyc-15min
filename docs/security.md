# Security

- No secrets are in the repo. Keys live in Render's environment settings, GitHub's repository secrets, and git-ignored local files (`server/.env`, `client/.env.local`); the `.env.example` files show the names only. The site holds only Supabase's publishable key, which can't read or write any table.
- No SQL is written by hand. The API reaches the database through Supabase's REST API with every value sent as a parameter: user ids come from a verified sign-in token, saved-place ids must be UUIDs, and everything else is checked before use.
- React escapes all text it renders, including place names from OpenStreetMap and saved-place names. The few map markers built from HTML use fixed strings only.
- The site sends a Content-Security-Policy (set in `render.yaml`) that allows scripts only from itself and connections only to the API, the map tiles, and Supabase. Both the site and the API send `nosniff`, HSTS, and headers that forbid other sites from framing them.
- The API accepts requests only from the site's address (CORS), limits each visitor to 30 searches a minute, and has its interactive docs turned off on Render. The rate limit identifies visitors by the address Cloudflare and Render add to `X-Forwarded-For`, counted from the end of the list, so a made-up header can't get around it.
- Dependabot (`.github/dependabot.yml`) opens weekly pull requests for outdated or vulnerable Python packages, npm packages, and GitHub Actions. A Tests workflow (`.github/workflows/tests.yml`) runs every test and a production build on each pull request and each push to `main`; Dependabot's minor and patch updates merge themselves once it passes, and major updates wait for a person with a comment saying so.

[Back to the README](../README.md)
