# How it works

1. **Walking network.** The five boroughs' walkable streets and paths come from OpenStreetMap, downloaded with OSMnx as one area, water included, so the bridges between boroughs come with it and streets that cross a borough line stay joined. The graph has 344,054 nodes and 531,590 segments (November 2026), each with its length in meters and the shape of curved paths, plus its street corners and crosswalk ends, for wheelchair mode (step 9). It's kept as NumPy arrays (`server/graph.py`): 62 MB in memory, loaded in 0.2 seconds, where Python dicts and lists took 366 MB and 8 seconds.
2. **Nearest street point.** A click snaps to the nearest graph node using a k-d tree (scipy's `cKDTree`), which checks a handful of nodes instead of all of them. Clicks on water, more than 150 m from any path, or on land where nobody lives are turned away with a message. That land is parks, cemeteries, golf courses, nature areas and wetlands, airports, and prisons, from OpenStreetMap outlines in `server/data/parks.json` ("That's in Woodlawn Cemetery. Pick a spot on a nearby street."), and the islands listed in `server/geo/not_lived_on.json`, such as Rikers and Randall's and Wards ("Rikers Island has no residential areas."). Any other island with almost no paths, like the marshes in Jamaica Bay, gets "This island has no residential areas."; the server finds those from the walking graph when it starts. Clicks in the rivers, bays, and ocean inside the city's limits name the water, from OpenStreetMap data in `server/data/waterways.json`: "That's in the East River. Pick a spot on land." Smaller water (Flushing Bay, the Gowanus Canal) has an outline to be inside. The big rivers and bays don't, because OpenStreetMap maps them as part of the sea, so the name comes from the nearest river center line within about 1.3 km, or bay label point within about 4 km. Unnamed open water south of Coney Island and the Rockaways is the Atlantic Ocean.
3. **15-minute search.** Dijkstra's algorithm spreads out from that node at 80 m per minute and stops at 15 minutes. It runs in scipy's compiled code, with each edge in minutes, so its sums match the pure-Python version it replaced to the last digit. Because it stops at 15 minutes, it visits only the 1,500 or so nodes in reach, whatever the size of the city: about a millisecond.
4. **Walking area.** Every reached street segment is widened by 40 m on a grid of 10 m squares in NumPy: points every 5 m along the streets mark their squares, SciPy grows the marks by 40 m and fills the holes (block interiors, lawns), and the marked squares become one Shapely shape. Widening each segment with Shapely and merging them took about 100 ms of CPU, over a second on Render's free plan, which gives the API a tenth of a CPU. The grid takes about a sixth of that, and the outline moves by a few meters (`server/scripts/time_area.py`). The shape is then cut to the city's shoreline (`server/geo/boroughs.json`) minus its lakes and ponds. Segments that the time limit cuts off partway are drawn only as far as the time allows. Finished areas are kept in memory, and in Redis for 30 days (`server/shared_cache.py`), so they survive the free API going to sleep.
5. **Places.** About 8,500 groceries, pharmacies, doctors and clinics, parks, schools, and subway stations (including the Staten Island Railway) from OpenStreetMap, each attached to the graph. A park counts as reached when any path into it is reached. The server matches a walk against all of them at once with NumPy (`server/amenities.py`).
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

   The decay shape follows Yang et al. (2023), who scored Shanghai's 15-minute life circles. Counting several places per category and weighting groceries highest follow Walk Score. Both use full points up to 5 minutes, which scored almost all of Manhattan 97–99, so this version uses 3 minutes and counts more places. Across 150 random points in Manhattan the median is 78. The panel also shows proximity time, the average minutes to the nearest place in each category, adapted from Bruno et al. (2024).

7. **Your needs.** The weights above are the defaults. Under "Needs" in the panel, anyone can start from a preset (Student, Parent, Retiree) and set each category to Not needed, Nice to have, Important, or Essential, which are weights 0 to 3. A category set to Not needed is still listed but is left out of the score and of proximity time. Changing a setting re-requests only the score, not the shaded area, and the browser remembers the choice.

   | Preset | Groceries | Subway | Pharmacies | Doctors | Parks | Schools |
   | --- | --- | --- | --- | --- | --- | --- |
   | Default | 3 | 2 | 1 | 1 | 1 | 1 |
   | Student | 3 | 3 | 1 | 1 | 2 | 0 |
   | Parent | 3 | 2 | 2 | 2 | 3 | 3 |
   | Retiree | 3 | 2 | 3 | 3 | 2 | 0 |

   The presets are my own judgment calls, not survey results.

8. **Time of day.** By default every place counts, whatever its hours. Move the "Open at" slider, or press Now, and the score only counts places open at that hour today, New York time. Hours come from OpenStreetMap's `opening_hours` tag, read on the server with [opening-hours-py](https://pypi.org/project/opening-hours-py/). Closed places leave the map, and the panel lists them as "Closed at 9 pm" with a count such as "3 of 5 open". Places with no listed hours still count and get a "?" badge. The subway runs all night and schools matter for being nearby, so those two are always counted.

9. **Wheelchair.** "Needs" starts with how you get around: Walking or Wheelchair. In a wheelchair the search moves at 48 m a minute instead of 80, about 0.8 m/s, the everyday average in Cooper et al. (2011) and Tolerico et al. (2007). Each street corner or crosswalk end with no curb ramp within 30 m adds 3 minutes, roughly the detour to the next corner that has one. That penalty is my estimate, not a measured value. Ramps come from NYC DOT's [Pedestrian Ramp Locations](https://data.cityofnewyork.us/d/ufzp-rrqu). Corners without a ramp show on the map as dark diamonds with "!", and the line under the score says how many are in reach. The penalty applies whenever the search passes such a corner, even where it walks along the street rather than crossing it.

10. **All of New York City.** A script (`server/scripts/build_grid.py`) lays a 100 m grid over the five boroughs, 70,779 squares near a street or path, and runs the same 15-minute walk from each one, saving every category's score. It takes about 3 minutes on GitHub Actions and runs after each monthly data refresh. It needs only NumPy: which squares are on land, in water, or in a park is worked out a whole row of the grid at a time, by finding where the outlines cross that row. Nobody lives in parks, cemeteries, golf courses, nature areas, airports, or prisons, or on Randall's, Governors, Liberty, Ellis, Rikers, Hart, and North and South Brother Islands, so those squares are left out of the rank, the gaps, and the search for a best spot. The grid is saved as one file per borough (70 to 245 KB compressed), with each square as nine small numbers: its column and row on the grid, its six scores, and flags for the categories with nothing in reach. With the grid:
    - Each clicked spot gets a rank under its score, such as "Better than 70% of Brooklyn and 64% of the city", using the same weights as the score. The grid was scored walking at any time, so the rank only shows for those settings.
    - **Score map** (a button at the top of the map): a smooth heat map of the score with your weights, colored with the viridis palette, which stays in order for color-blind viewers. The squares are data points, not drawn shapes: the browser (`client/src/data/gridImage.js`) sets each pixel to a weighted average of the nearby squares' scores, with weights falling off along a Gaussian curve (sigma 120 m), and divides by the total weight so the shore and small parks don't fade. Only the area around the view is drawn, at up to 2.5 million pixels, into a canvas the map stretches along with each zoom. The area is twice the view's width and height, so panning half a screen or zooming out one level shows color that's already there; a new image is drawn only when the map moves past it or zooms in two levels. The canvas goes on the map as it is, without being turned into a PNG first, which took longer than the drawing. The image is cut to the shoreline, with lakes cut out. Parks have no score of their own, so they take the colors of the blocks around them: where the normal smoothing has no data, a wider one (sigma 500 m) takes over, which reaches the middle of Central Park without leaving holes.
    - **Gap finder**: for one category, the areas with nothing of it within 15 minutes, drawn the same smooth way in the category's color (darker where more nearby squares are gaps), and, in each borough, the one square where a new place would cover the most gap squares, marked with a star. The panel describes the borough at the middle of the map. The spot is named by its nearest corner, using the street names in the curb ramp data, or else by the nearest named place. The gaps are uneven. In the November 2026 data, of the squares where people live:

      | Borough | Squares | No grocery | No subway station | No pharmacy |
      | --- | ---: | ---: | ---: | ---: |
      | Manhattan | 4,667 | 16 | 80 | 21 |
      | Bronx | 8,107 | 1,883 | 2,733 | 2,452 |
      | Brooklyn | 14,949 | 1,074 | 3,400 | 2,531 |
      | Queens | 21,487 | 3,124 | 14,046 | 5,657 |
      | Staten Island | 9,860 | 4,266 | 7,068 | 3,812 |

    - The site serves the grid files itself (copied in at build time by `client/scripts/fetch-grid.mjs`), so the score map works while the API sleeps. Their names include their fingerprints, so browsers keep them for a year, and only the boroughs in view are loaded.
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
- The panel puts the answer first: the score, then each category's nearest place, then the settings. "Open" and "Needs" are each one closed line with their current value ("Open: Any time", "Needs: Default, walking"). Opened, "Open" has Any time, Now, and Pick a time, and the hour slider only shows for Pick a time; "Needs" shows Walking or Wheelchair and the presets, and the six importance menus are one more click in, under "Customize".
- The hour is a native slider, so arrow keys work, and screen readers read the hour as "9 pm".
- Map markers carry meaning in shape and symbol, not only color: places with no listed hours get a "?" badge, corners without curb ramps are diamonds with "!", and the gap finder's best spot is a star.
- Controls that change the map sit on the map, as in other map apps: "Your walk / Score map / Gap finder" and a "Go to…" menu of boroughs float over its top edge, with Leaflet's zoom buttons moved below them. While the score map or gap finder is on, a box at the top of the panel names it and the borough at the middle of the map, and explains it in words (the legend labels the scale with numbers and both ends in words, and the gap finder names the best spot by its cross streets). "Your walk" or a click on the map goes back.
- The map opens on Manhattan and covers the five boroughs. Everything outside the city's legal boundary, which runs through the rivers and bays, is greyed out, however far the map is zoomed out. "Go to…" flies the map to each borough, so no borough needs dragging to.
- Account forms have visible labels, fill in from password managers (`autocomplete`), and show each error under its field, announced to screen readers. Dialogs use the native `<dialog>`, so focus stays inside and Escape closes them.
- Deleting an account is set apart in red and takes a second step, where "Keep account" is the default and has the focus.

- A spot can be chosen without the map: "Search an address" at the top of the panel suggests addresses as you type, from NYC Planning Labs' [GeoSearch](https://labs-geosearch-docs.netlify.app/docs), which is built on the city's own address database and needs no key. It follows the ARIA combobox pattern: the arrow keys move through the suggestions, Enter picks one (or the first), Escape closes the list, and screen readers hear how many suggestions there are. Picking one flies the map there and runs the same search as a click.

[Back to the README](../README.md)
