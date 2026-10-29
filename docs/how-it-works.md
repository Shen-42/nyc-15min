# How it works

1. **Walking network.** Manhattan's walkable streets and paths come from OpenStreetMap, downloaded once with OSMnx and saved as a graph: 36,790 nodes and 57,619 segments, each with its length in meters and the shape of curved paths. The graph also lists its street corners and crosswalk ends, for wheelchair mode (step 9).
2. **Nearest street point.** A click snaps to the nearest graph node using a grid index (0.002° cells, searched in growing rings), about 20 times faster than checking every node. Clicks on water, inside a park (nobody lives there; outlines from `server/data/parks.json`), or more than 150 m from any path are turned away with a message.
3. **15-minute search.** Dijkstra's algorithm with a binary heap spreads out from that node at 80 m per minute and stops at 15 minutes. From Times Square it reaches about 1,800 nodes in a few milliseconds.
4. **Walking area.** Every reached street segment is widened by 40 m and merged with Shapely, holes such as block interiors are filled, and the result is cut to Manhattan's shoreline minus its lakes and ponds. Segments that the time limit cuts off partway are drawn only as far as the time allows.
5. **Places.** About 1,900 groceries, pharmacies, doctors and clinics, parks, schools, and subway stations from OpenStreetMap, each attached to the graph. A park counts as reached when any path into it is reached.
6. **Score.** Each category earns points from its nearest few places, full points within 3 minutes and falling along a bell curve after that (50% at 8 minutes). Categories are then weighted:

   ```
   f(t)  = 1 if t ≤ 3 min, else exp(-(t − 3)² / 36)
   S_c   = Σ depthᵢ · f(tᵢ)       over the k nearest places in category c
   score = 100 · Σ w_c · S_c / Σ w_c
   ```

   | Category | Weight | Places counted |
   | --- | --- | --- |
   | Groceries | 3 | 5 |
   | Subway stations | 2 | 3 |
   | Pharmacies | 1 | 3 |
   | Doctors and clinics | 1 | 2 |
   | Parks | 1 | 2 |
   | Schools | 1 | 2 |

   The decay shape follows Yang et al. (2023), who scored Shanghai's 15-minute life circles. Counting several places per category and weighting groceries highest follow Walk Score. Both use full points up to 5 minutes, which scored almost all of Manhattan 97–99, so this version uses 3 minutes and counts more places. Across 150 random points the median is 78. The panel also shows proximity time, the average minutes to the nearest place in each category, adapted from Bruno et al. (2024).

7. **Your needs.** The weights above are the defaults. Under "Your needs" in the panel, anyone can start from a preset (Student, Parent, Retiree) and set each category to Not needed, Nice to have, Important, or Essential, which are weights 0 to 3. A category set to Not needed is still listed but is left out of the score and of proximity time. Changing a setting re-requests only the score, not the shaded area, and the browser remembers the choice.

   | Preset | Groceries | Subway | Pharmacies | Doctors | Parks | Schools |
   | --- | --- | --- | --- | --- | --- | --- |
   | Default | 3 | 2 | 1 | 1 | 1 | 1 |
   | Student | 3 | 3 | 1 | 1 | 2 | 0 |
   | Parent | 3 | 2 | 2 | 2 | 3 | 3 |
   | Retiree | 3 | 2 | 3 | 3 | 2 | 0 |

   The presets are my own judgment calls, not survey results.

8. **Time of day.** By default every place counts, whatever its hours. Move the "Open at" slider, or press Now, and the score only counts places open at that hour today, New York time. Hours come from OpenStreetMap's `opening_hours` tag, read on the server with [opening-hours-py](https://pypi.org/project/opening-hours-py/). Closed places leave the map, and the panel lists them as "Closed at 9 pm" with a count such as "3 of 5 open". Places with no listed hours still count and get a "?" badge. The subway runs all night and schools matter for being nearby, so those two are always counted.

9. **Wheelchair.** "Your needs" starts with how you get around: Walking or Wheelchair. In a wheelchair the search moves at 48 m a minute instead of 80, about 0.8 m/s, the everyday average in Cooper et al. (2011) and Tolerico et al. (2007). Each street corner or crosswalk end with no curb ramp within 30 m adds 3 minutes, roughly the detour to the next corner that has one. That penalty is my estimate, not a measured value. Ramps come from NYC DOT's [Pedestrian Ramp Locations](https://data.cityofnewyork.us/d/ufzp-rrqu). Corners without a ramp show on the map as dark diamonds with "!", and the line under the score says how many are in reach. The penalty applies whenever the search passes such a corner, even where it walks along the street rather than crossing it.

10. **All of Manhattan.** A script (`server/scripts/build_grid.py`) lays a 100 m grid over the island, about 5,450 squares on land, and runs the same 15-minute walk from each one, saving every category's score. It takes under a minute and runs after each monthly data refresh. Nobody lives in a park, so squares that lie mostly inside a park outline from OpenStreetMap (saved by `build_amenities.py` as `server/data/parks.json`) are left out of the rank, the gaps, and the search for a best spot. On the gap finder, every park outline and lake is cut out of the image, and color also fades wherever most nearby squares are park (such as the Henry Hudson Parkway's strip through Inwood Hill Park), so no gap is ever shown in a park. With the grid:
    - Each clicked spot gets a rank under its score, such as "Better than 70% of Manhattan", using the same weights as the score. The grid was scored walking at any time, so the rank only shows for those settings.
    - **Score map** (under "Map view"): a smooth heat map of the score with your weights, colored with the viridis palette, which stays in order for color-blind viewers. The squares are data points, not drawn shapes: the browser (`client/src/data/gridImage.js`) sets each pixel to a weighted average of the nearby squares' scores, with weights falling off along a Gaussian curve (sigma 120 m), and divides by the total weight so the shore and small parks don't fade. The image is cut to Manhattan's shoreline, with lakes cut out. Parks have no score of their own, so they take the colors of the blocks around them: where the normal smoothing has no data, a wider one (sigma 500 m) takes over, which reaches the middle of Central Park without leaving holes. It's rebuilt in about 0.2 seconds when your weights change.
    - **Gap finder**: for one category, the areas with nothing of it within 15 minutes, drawn the same smooth way in the category's color (darker where more nearby squares are gaps), and the one square where a new place would cover the most gap squares, marked with a star. The spot is named by its nearest corner, using the street names in the curb ramp data, or else by the nearest named place. Manhattan has few true gaps. In the October 2026 data, of 4,720 squares outside parks: 15 have no grocery store in reach (11 of them on Roosevelt Island), 83 no subway station (the largest group, 27 squares, on the Lower East Side), 61 no pharmacy (38 in Inwood), and none lack a park.

11. **Accounts (optional).** Searching never needs an account. Signing in, with email and password through [Supabase Auth](https://supabase.com/docs/guides/auth), lets you save places and keep your needs profile across devices.
    - The browser only uses Supabase to sign in. Saves, loads, and deletes go through the API, which checks the sign-in token itself against Supabase's public keys (`server/auth.py`) and filters every query by the signed-in user (`server/store.py`).
    - The two tables (`supabase/schema.sql`) have row-level security on with no policies, so the browser's public key can't read or write them; only the API's secret key can.
    - Two roles. A **user** manages only their own saved places, profile, and account. An **admin**, listed by user id in the API's `ADMIN_USER_IDS` setting, also sees the last week's search counts and can start the monthly data refresh. The server checks the role on every admin request and answers 403 otherwise.
    - Edge cases handled: a session that expires mid-visit is refreshed once, then signs out with a message; signing in before confirming the email offers to resend the link; signing up twice with the same email says the account exists; password reset by email; two tabs editing the same profile (each save names the version it started from, and an out-of-date save is refused with the latest profile, which the page then shows); deleting an account removes its saved places, profile, and sign-in.
    - Free Supabase projects pause after a week without use, so a small GitHub Actions job (`keep-supabase-awake.yml`) queries the database twice a week.

12. **When things go wrong.** Every message appears in one place under the title, in one style, saying what happened and what to do next. Errors that a second try might fix (no connection, a timeout, a server error) come with a **Try again** button, and keyboard focus moves to it; refusals such as a click in a park or too many searches don't, since trying again wouldn't help.
    - Requests give up after 70 seconds, longer than the free API takes to wake up, instead of spinning forever.
    - The shaded area, the slowest request, is tried a second time before the panel says it couldn't be drawn; the score and places still show.
    - A crash in the map or the panel shows a message and a **Reload the page** button in its place, instead of a blank page; the other part keeps working.
    - On the server, any error a route doesn't handle is logged with the request that caused it and answered with a plain message and a short request id (also in the `X-Request-ID` header of every response), so a visitor's report can be matched to the log. FastAPI's own input errors come back as one readable sentence.

## Design and accessibility

- Mobile first: on phones the results sit in a bottom sheet over a full-screen map; from 768 px up they move to a side panel. The sheet has three positions: open (settings and categories), peek (just the title and score), and hidden (just the handle, so the whole map shows). Swipe up or down to move between them, or tap the handle to step hidden → peek → open → peek; the handle is a button, so it works by keyboard and screen reader too. Clicking the map brings a hidden sheet back to peek so the new score shows. Whatever is off screen is skipped by Tab.
- Text contrast is at least 4.5:1 (WCAG 1.4.3), and every category color is at least 5:1 under white text.
- Categories have letters as well as colors (G, T, Rx, +, P, S), so color is never the only cue (WCAG 1.4.1).
- Buttons and rows are at least 44 px tall, and keyboard focus is always visible.
- Score changes are announced to screen readers, and animations respect the reduced-motion setting.
- The time and "Your needs" settings start closed, so the panel shows the score and categories first. Their current values show on the closed line, e.g. "Time: Open at 9 pm".
- The hour is a native slider, so arrow keys work, and screen readers read the hour as "9 pm".
- Map markers carry meaning in shape and symbol, not only color: places with no listed hours get a "?" badge, corners without curb ramps are diamonds with "!", and the gap finder's best spot is a star.
- The score map and gap finder are off until chosen under "Map view". While one is on, a box at the top of the panel names it, explains it in words (the legend labels the scale with numbers and both ends in words, and the gap finder names the best spot by its cross streets), and has a "Back to your walk" button. Clicking the map also goes back.

- Account forms have visible labels, fill in from password managers (`autocomplete`), and show each error under its field, announced to screen readers. Dialogs use the native `<dialog>`, so focus stays inside and Escape closes them.
- Deleting an account is set apart in red and takes a second step, where "Keep account" is the default and has the focus.

Not yet supported: choosing a point by keyboard. An address search would fix that.

[Back to the README](../README.md)
