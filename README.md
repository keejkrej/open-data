# StatsBomb Open Data

Welcome to the StatsBomb Open Data repository.

StatsBomb are committed to sharing new data and research publicly to enhance understanding of the game of Football. We want to actively encourage new research and analysis at all levels. Therefore we have made certain leagues of StatsBomb Data freely available for public use for research projects and genuine interest in football analytics.

StatsBomb are hoping that by making data freely available, we will extend the wider football analytics community and attract new talent to the industry.

## Terms & Conditions

If you publish, share or distribute any research, analysis or insights based on this data, please state the data source as StatsBomb and use our logo, available in our [Media Pack](https://statsbomb.com/media-pack/).

## Getting Started

The [data](./data/) is provided as JSON files exported from the StatsBomb Data API, in the following structure:

* Competition and seasons stored in [`competitions.json`](./data/competitions.json).
* Matches for each competition and season, stored in [`matches`](./data/matches/). Each folder within is named for a competition ID, each file is named for a season ID within that competition.
* Events and lineups for each match, stored in [`events`](./data/events/) and [`lineups`](./data/lineups/) respectively. Each file is named for a match ID.
* StatsBomb 360 data for selected matches, stored in [`three-sixty`](./data/three-sixty/). Each file is named for a match ID.

Some documentation about the meaning of different events and the format of the JSON can be found in the [`doc`](./doc) directory.

## Visualising events

A small package under [`src/open_data_viz/`](./src/open_data_viz/) renders events that have 360 freeze-frame data as PNG frames and an MP4 video. Each frame shows the pitch, the visible area, every tracked player (teammate/opponent/actor/keeper), the ball, plus an arrow for passes and shots.

```bash
# Install dependencies and run
uv sync

# Render all Pass and Shot events for a match into frames/<match_id>/
uv run viz-events 3764440 --types Pass Shot

# Same, but also encode an MP4 at 6 fps
uv run viz-events 3764440 --types Pass Shot --video events.mp4 --fps 6
```

Requires: `uv`, `ffmpeg`. Python dependencies are managed by `uv` via `pyproject.toml`.

## Careers

If you're interested in football data, [StatsBomb is always hiring!](https://statsbomb.bamboohr.com/jobs/)
