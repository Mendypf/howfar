---
name: "howfar"
description: "How far away is the thing in this photo or video: a building, a mountain, something down the road, and how long it takes to walk or drive there. Use whenever someone shares a photo or a slow turning video and asks how far, how big, what is that, or how long to get to it."
metadata: { "includeInPrompt": true }
---

# How far

## Purpose
Answer "how far is that?" from a phone photo (or a slow 360-degree turn on video) plus the person's location. The
tools here read open map data (building outlines with heights, terrain, named mountains, roads) and do the geometry.
YOU do the looking: naming a landmark, matching the photo to a drawn map, picking from a shortlist. No keys, no accounts.

## Tooling
Run with `exec`: `python3 <skill dir>/bin/howfar.py <command> ...`. Every command prints one JSON object; pictures for
you to look at go to `--out` (default `./howfar_out`). First use: `pip install -r <skill dir>/requirements.txt`
(requests, numpy, Pillow). The spin command also needs `ffmpeg` on the path.

Commands:
- `look PHOTO [--lat --lon] [--utc] [--out DIR]` what the file says (GPS, time, lens, compass hint and its known quirks),
  what is around that spot (roads at the user's feet with their exact bearings, named or tall buildings, named mountains with
  whether they are hidden, the sun's direction), and three pictures: `map.png` (north-up block map), `around.png`
  (360-degree eye-level view drawn from the map, compass bearings along the edges), `photo_ruled.jpg` (the photo with a 0-100
  percent grid). Pass `--lat --lon` from the user's location when the file has no GPS (uploads often strip it).
- `anchor --lat --lon --name "Space Needle" --x 0.21 --y 0.31 --w W --h H --f35 F` one thing you recognised in the photo plus
  the spot of its TOP (percent grid read as fractions) gives the camera heading to about 1 degree and the tilt.
- `aim --lat --lon --heading H --tilt T --x X --y Y --w W --h H --f35 F [--kind building|mountain|ground|any]` or
  `aim --lat --lon --bearing B --elevation E` what the line of sight hits: buildings the lines land on (votes), the ground,
  named peaks near the line, a `verdict` with a range, and `shortlist_if_heading_is_rough` for compass-grade headings.
- `spin VIDEO --lat --lon [--utc] [--hfov 65]` a slow full turn: builds a 360 strip (`strip_ruled.jpg`), matches its skyline
  to `around.png` without AI, and checks the sun. The target is what the video ENDS on.
- `peak --lat --lon --name "Half Dome"` trail distance, time and climb to a mountain, on real trails.
- `drive --lat --lon --to-lat --to-lon` road distance and minutes.
- `sunpos`, `clear-cache`.

## Workflow: a photo
1. `look`. Read `photo.notes` and `compass_hint.note`. If there is no position, ask for it or use the message location.
2. Open `photo_ruled.jpg`. Decide which heading source you have, in this order:
   a. **A landmark you recognise** (a famous tower, a named mountain, a named building from `named_buildings_near` or
      `named_mountains_around`): read the spot of its top off the grid, run `anchor`. Best: about 1 degree.
   b. **The road**: if the photo looks along the road the user stands on, the heading is one of the two bearings in
      `roads_at_your_feet` (the compass hint, even a bad one, says which of the two). Good: a few degrees.
   c. **Map match**: compare the photo with `map.png` AND `around.png` and name the bearing yourself. Only trust it when
      both pictures agree within 25 degrees; otherwise ask the user one question: "is the sun ahead, behind, left or right
      of you?" (`sun` in `look` gives the sun's bearing) or "what is the road to your left called?".
   d. **The phone compass** alone: rough, often 10 degrees off (Pixel: direction of the TOP EDGE, so landscape shots are 90 off).
3. Read the target's spot off the grid (aim at its base or its middle, not a spire tip). Run `aim` with the heading and tilt from
   `anchor`, or `--bearing/--elevation` if you worked the line out another way. Use `--kind mountain` for peaks.
4. Answer from `verdict`. With a heading from (d), do not answer from `verdict`; pick from `shortlist_if_heading_is_rough`
   by eye (name, height, floors, colour, what it looks like) and say which one you picked and why.

## Workflow: a spin video
1. Ask for a slow full turn (about 10 seconds), ending on the thing they mean. Run `spin` with the user's location.
2. Open `strip_ruled.jpg` and `around.png`; match them yourself and name the bearing at the strip's left edge.
3. You now have up to three readings: yours, `skyline_match`, `sun`. Two within 20 degrees: trust it. Otherwise say so and
   ask the sun question. Then `aim --bearing <last frame bearing> --elevation 0` (or the elevation you read).

## Workflow: a mountain, "how long to get there"
1. Identify the peak (anchor it, or `aim --kind mountain`). 2. `peak --name`. 3. Give trail km, minutes and climb, and say
   when the trail ends short of the summit (`off_trail_at_end_m`). Straight-line distance is not the hiking distance.

## Workflow: driving
A passenger shoots, never the driver. While moving, the direction of travel is the heading: the road's bearing from
`roads_at_your_feet` (forward is the one the photo looks along). Things ahead are answered as road distance and minutes
with `drive`, not as a straight line.

## Operating Rules
1. Say what you measured to: "about 420 m to the near face of the brick building", "97 km to the summit".
2. Always give the range from `verdict`. GPS alone is 5 to 10 m; in a street canyon it can be 30 m.
3. When the line hits nothing on the map, or the shortlist is a coin toss, say "I cannot tell between X and Y" and ask one
   question. Never give a single confident number for a guess.
4. Things that are not on a map (cars, people, boats, trees) are not measured; say so, and offer a rough eye estimate
   labelled as such if the user wants one.
5. Indoors, through glass, or with no GPS: say the tool does not work there.
6. Add the credit line from the JSON once per answer: map data from Overture Maps / OpenStreetMap contributors, terrain
   from Mapzen / AWS Open Data, mountains from Wikidata, routes from FOSSGIS Valhalla and BRouter.
7. Privacy: lookups send the map servers only tile numbers (a few km square) and the mountain query a box around the user.
   Map pieces are cached in `~/.cache/howfar`; `clear-cache` wipes them.
