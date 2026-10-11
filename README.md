# How far

You are standing somewhere, you point your phone at a building or a mountain,
and you want to know how far away it is. Your phone knows where you are. The
hard part is which way the camera was pointing, because the compass inside a
phone is off by ten degrees on a good day, and a map can only tell you what you
hit if the line is right.

This is a skill you add to an AI agent (Meta's Muse, Claude, ChatGPT, Gemini,
anything that can run a script and look at a picture). You send the photo, the
agent runs the tools here, looks at what they draw, and answers with a distance
and a range: "about 420 m to the brick building across the river", "Mount
Rainier, 97 km". For a mountain it can also tell you how long the walk is on
hiking trails, and while you are driving it answers in road miles and
minutes.

The tools read open map data (building outlines with
heights, terrain, named mountains, roads) and do the geometry. The agent does
the looking: it recognises a landmark in the photo, or matches the photo to a
map the tools draw, and that fixes the direction. Then a line of sight goes out
over the map and whatever it lands on is the answer, with its range.

If you can, take a slow full turn on video instead of one photo, and end on the
thing you mean. The whole street is in the clip, so the direction is far easier
to find, and on a sunny day the frame where the sun blows out the picture gives
the direction outright.

There are no keys and no accounts to set up. Everything comes from public open data: Overture Maps
and OpenStreetMap for buildings and roads, the AWS terrain tiles for ground
heights, Wikidata for mountains, the FOSSGIS Valhalla and BRouter servers for
routes.

## Install

Python 3.9 or newer, and `ffmpeg` if you want the video spin.

```bash
git clone https://github.com/Mendypf/howfar.git
cd howfar
pip install -r requirements.txt
```

For Muse, copy the folder to `~/workspace/skills/howfar/`. For Claude Code,
Cursor or Codex, point the agent at `SKILL.md`; it holds the whole procedure.

## Try it without an agent

```bash
python bin/howfar.py look photo.jpg --out out        # what the file says + what is around you + three pictures
python bin/howfar.py anchor --lat 47.63 --lon -122.36 --name "Space Needle" --x 0.21 --y 0.31 --w 4032 --h 3024 --f35 29
python bin/howfar.py aim --lat 47.63 --lon -122.36 --heading 136 --tilt 2.1 --x 0.78 --y 0.45 --w 4032 --h 3024 --f35 29 --kind mountain
python bin/howfar.py peak --lat 37.7305 --lon -119.5731 --name "Half Dome"
python bin/howfar.py drive --lat 47.6097 --lon -122.3331 --to-lat 47.9790 --to-lon -122.2021
python bin/howfar.py spin turn.mp4 --lat 55.683 --lon 12.574
```

Every command prints one JSON block. The pictures (`map.png`, `around.png`,
`photo_ruled.jpg`, `strip_ruled.jpg`) are what the agent looks at.

## What to expect

I tested it on public phone photos with known answers (`tests/regression.py`):

- A famous tower or a named mountain somewhere in the photo: the other things
  in the picture come out within 3%. Mount Rainier from Seattle, 97.6 km
  against a true 97.5. The Space Needle, 1.27 km against 1.31.
- Only the phone's compass, up to 13 degrees off: the right tower is in the
  shortlist the agent sees, and the distance is within 10% once it picks it.
- A full-turn video in a city: the direction came out within 19 degrees by all
  three methods on the test set. In villages and open country, where the map
  has few buildings, the methods disagree and the agent says it cannot tell.

What it does not do: measure things that are not on a map (cars, people,
trees), work indoors or through glass, or help where there is no GPS. GPS
itself is 5 to 10 m off, more between tall buildings, and that is in every
range it prints.

## Privacy

Nothing leaves your machine except the map requests: tile numbers (a few km
square) to the Overture and terrain servers, a box around your position to
Wikidata, and the two end points to the routing servers. Downloaded map pieces
sit in `~/.cache/howfar`; `python bin/howfar.py clear-cache` deletes them.

## Credits

Map data from the Overture Maps Foundation and OpenStreetMap contributors
(ODbL). Terrain tiles from Mapzen and the AWS Open Data program. Mountains from
Wikidata (CC0). Routing by the FOSSGIS Valhalla server and BRouter, both run as
free public services; one request per question, please. MIT licence.
