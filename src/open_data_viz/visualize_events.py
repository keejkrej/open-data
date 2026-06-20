#!/usr/bin/env python3
"""
Render StatsBomb event + 360 data as PNG frames and an MP4 video.

Each frame shows one event that has 360 freeze-frame data:
  - pitch outline
  - visible area polygon from the 360 frame
  - all tracked players as points (teammates/opponents, actor/keeper)
  - the ball at the event location
  - arrows for pass / shot destinations
  - event metadata as text

Usage:
    uv run viz-events <match_id> [--types Pass Shot] [--output-dir frames/]

Requires: matplotlib, Pillow, ffmpeg (for MP4)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, Polygon, Rectangle
import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[2]
PITCH_LENGTH = 120.0   # StatsBomb native units
PITCH_WIDTH = 80.0


def load_match_data(match_id: int, data_dir: Path):
    events_path = data_dir / "events" / f"{match_id}.json"
    three60_path = data_dir / "three-sixty" / f"{match_id}.json"
    lineups_path = data_dir / "lineups" / f"{match_id}.json"

    if not events_path.exists():
        raise FileNotFoundError(f"No events file for match {match_id}: {events_path}")

    events = json.loads(events_path.read_text())
    event_by_id = {e["id"]: e for e in events}

    three60 = []
    if three60_path.exists():
        three60 = json.loads(three60_path.read_text())

    lineups = []
    if lineups_path.exists():
        lineups = json.loads(lineups_path.read_text())

    return events, three60, lineups, event_by_id


def draw_pitch(ax, length: float = PITCH_LENGTH, width: float = PITCH_WIDTH, color: str = "#cccccc"):
    """Draw a football pitch in StatsBomb coordinates (0,0 -> 120,80)."""
    ax.set_xlim(0, length)
    ax.set_ylim(0, width)
    ax.set_aspect("equal")
    ax.axis("off")

    # Outer border
    border = Rectangle((0, 0), length, width, linewidth=2, edgecolor=color, facecolor="none")
    ax.add_patch(border)

    # Halfway line
    ax.plot([length / 2, length / 2], [0, width], color=color, linewidth=2)

    # Centre circle
    center_circle = Circle((length / 2, width / 2), 9.15, fill=False, edgecolor=color, linewidth=2)
    ax.add_patch(center_circle)
    ax.plot(length / 2, width / 2, "o", color=color, markersize=6)

    # Penalty areas
    box_width = 40.32
    box_depth = 16.5
    six_yard_width = 18.32
    six_yard_depth = 5.5

    # Left penalty area
    ax.add_patch(Rectangle((0, (width - box_width) / 2), box_depth, box_width,
                            fill=False, edgecolor=color, linewidth=2))
    # Right penalty area
    ax.add_patch(Rectangle((length - box_depth, (width - box_width) / 2), box_depth, box_width,
                            fill=False, edgecolor=color, linewidth=2))

    # Left six-yard box
    ax.add_patch(Rectangle((0, (width - six_yard_width) / 2), six_yard_depth, six_yard_width,
                            fill=False, edgecolor=color, linewidth=2))
    # Right six-yard box
    ax.add_patch(Rectangle((length - six_yard_depth, (width - six_yard_width) / 2),
                            six_yard_depth, six_yard_width, fill=False, edgecolor=color, linewidth=2))

    # Penalty spots
    ax.plot(11, width / 2, "o", color=color, markersize=4)
    ax.plot(length - 11, width / 2, "o", color=color, markersize=4)

    # Penalty arcs
    arc_left = Arc((11, width / 2), 18.3, 18.3, angle=0, theta1=308, theta2=52,
                   color=color, linewidth=2)
    arc_right = Arc((length - 11, width / 2), 18.3, 18.3, angle=0, theta1=128, theta2=232,
                    color=color, linewidth=2)
    ax.add_patch(arc_left)
    ax.add_patch(arc_right)

    # Goal areas
    goal_area_width = 18.32
    goal_area_depth = 2.0
    ax.add_patch(Rectangle((-goal_area_depth, (width - goal_area_width) / 2),
                            goal_area_depth, goal_area_width,
                            fill=False, edgecolor=color, linewidth=2))
    ax.add_patch(Rectangle((length, (width - goal_area_width) / 2),
                            goal_area_depth, goal_area_width,
                            fill=False, edgecolor=color, linewidth=2))


def format_event_text(event: Dict) -> str:
    """Build a concise description of the event."""
    parts = [
        f"{event.get('type', {}).get('name', 'Unknown')}",
    ]
    if "pass" in event:
        recipient = event["pass"].get("recipient", {}).get("name")
        if recipient:
            parts.append(f"→ {recipient}")
        height = event["pass"].get("height", {}).get("name")
        if height:
            parts.append(f"({height})")
    if "shot" in event:
        parts.append(f"from {event['shot'].get('type', {}).get('name', '')}")

    team = event.get("team", {}).get("name", "Unknown")
    player = event.get("player", {}).get("name", "Unknown")
    period = event.get("period", "?")
    minute = event.get("minute", "?")
    second = event.get("second", "?")
    ts = event.get("timestamp", "?")

    return (
        f"{event['id'][:8]} | P{period} {minute:02d}:{second:02d} ({ts})\n"
        f"{team} — {player}\n"
        f"{' '.join(parts)}"
    )


def render_frame(
    event: Dict,
    frame: Optional[Dict],
    output_path: Path,
    figsize: Tuple[int, int] = (12, 8),
    dpi: int = 150,
):
    """Render a single event to PNG. If frame is provided, overlay 360 players/visible area."""
    fig, ax = plt.subplots(figsize=figsize)
    draw_pitch(ax)

    has_360 = frame is not None

    if has_360:
        # Visible area polygon
        visible_area = frame.get("visible_area")
        if visible_area and len(visible_area) >= 6:
            pts = np.array(visible_area).reshape(-1, 2)
            poly = Polygon(pts, closed=True, facecolor="#1f4e1f", edgecolor="none", alpha=0.35)
            ax.add_patch(poly)

        # Players
        teammates_x, teammates_y = [], []
        opponents_x, opponents_y = [], []
        actor_loc = None
        keeper_locs = []

        for p in frame.get("freeze_frame", []):
            loc = p.get("location")
            if not loc or len(loc) < 2:
                continue
            x, y = loc
            if p.get("actor"):
                actor_loc = (x, y)
            elif p.get("keeper"):
                keeper_locs.append((x, y))
            elif p.get("teammate"):
                teammates_x.append(x)
                teammates_y.append(y)
            else:
                opponents_x.append(x)
                opponents_y.append(y)

        # Draw points
        ax.scatter(teammates_x, teammates_y, c="#3498db", s=120, edgecolors="white", linewidths=1,
                   zorder=5, label="teammate")
        ax.scatter(opponents_x, opponents_y, c="#e74c3c", s=120, edgecolors="white", linewidths=1,
                   zorder=5, label="opponent")
        for x, y in keeper_locs:
            ax.scatter(x, y, c="#f1c40f", s=200, marker="D", edgecolors="black", linewidths=1,
                       zorder=6, label="keeper")
        if actor_loc:
            ax.scatter(actor_loc[0], actor_loc[1], c="#2ecc71", s=250, marker="*",
                       edgecolors="black", linewidths=1.5, zorder=7, label="actor")

    # Ball at event location + pass/shot arrows
    loc = event.get("location")
    if loc and len(loc) >= 2:
        ax.scatter(loc[0], loc[1], c="white", s=90, marker="o", edgecolors="black", linewidths=2,
                   zorder=8)
        ax.scatter(loc[0], loc[1], c="black", s=30, marker="o", zorder=9)

        end_loc = None
        color = None
        if "pass" in event:
            end_loc = event["pass"].get("end_location")
            color = "#3498db"
        elif "shot" in event:
            end_loc = event["shot"].get("end_location")
            color = "#e67e22"
        if end_loc and len(end_loc) >= 2:
            ax.annotate("", xy=(end_loc[0], end_loc[1]), xytext=(loc[0], loc[1]),
                        arrowprops=dict(arrowstyle="->", color=color, lw=2.5, alpha=0.85),
                        zorder=7)

    # Event text box
    text = format_event_text(event)
    if not has_360:
        text += "\n(no 360 data — ball/arrows only)"
    ax.text(
        0.5, 0.98, text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        horizontalalignment="center",
        color="white",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="black", alpha=0.7, edgecolor="none"),
        zorder=10,
    )

    # Legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    if by_label:
        ax.legend(by_label.values(), by_label.keys(), loc="lower right",
                  facecolor="black", edgecolor="white", labelcolor="white", fontsize=8)

    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, facecolor="#2d5a27", edgecolor="none")
    plt.close(fig)


def build_video(frame_paths: List[Path], output_path: Path, fps: int = 6):
    """Stitch PNG frames into an MP4 using ffmpeg, holding each frame for 1/fps seconds."""
    if not frame_paths:
        print("No frames to encode.")
        return
    if output_path.exists():
        output_path.unlink()

    # Symlink frames into a temp dir with sequential names so ffmpeg can read a pattern.
    tmp_dir = output_path.parent / "_video_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    width = len(str(len(frame_paths)))
    for i, src in enumerate(frame_paths):
        link = tmp_dir / f"frame_{i:0{width}d}.png"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(src.resolve())

    pattern = tmp_dir / f"frame_%0{width}d.png"
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(pattern),
        "-vf", f"fps={fps},format=yuv420p",
        "-c:v", "libx264", "-r", str(fps),
        "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"Video saved: {output_path}")
    finally:
        for f in tmp_dir.iterdir():
            f.unlink()
        tmp_dir.rmdir()


def main():
    parser = argparse.ArgumentParser(description="Render StatsBomb event/360 frames as PNG and MP4")
    parser.add_argument("match_id", type=int, help="Match ID to visualize")
    parser.add_argument("--data-dir", type=str, default=str(ROOT_DIR / "data"),
                        help="Path to StatsBomb data directory")
    parser.add_argument("--types", nargs="+", default=None,
                        help="Filter event type names, e.g. Pass Shot Carry")
    parser.add_argument("--limit", type=int, default=None, help="Max number of events to render")
    parser.add_argument("--output-dir", type=str, default="frames",
                        help="Directory for PNG frames")
    parser.add_argument("--video", type=str, default="events.mp4",
                        help="Output MP4 filename (saved in output-dir)")
    parser.add_argument("--fps", type=int, default=6, help="Frames per second in output video")
    parser.add_argument("--no-video", action="store_true", help="Skip MP4 encoding")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    events, three60, lineups, event_by_id = load_match_data(args.match_id, data_dir)
    print(f"Loaded {len(events)} events, {len(three60)} 360 frames, {len(lineups)} lineups "
          f"for match {args.match_id}")

    has_360 = bool(three60)
    if not has_360:
        print("No 360 data — falling back to event-only rendering (ball/arrows only).")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    type_filter = {t.lower() for t in args.types} if args.types else None

    # Build an iterable of (event, optional_frame) tuples.
    # Prefer 360 frames where available; otherwise use all events with a location.
    items_to_render = []
    if has_360:
        for i, frame in enumerate(three60):
            event = event_by_id.get(frame["event_uuid"])
            if event is None:
                continue
            items_to_render.append((i, event, frame))
    else:
        for i, event in enumerate(events):
            if "location" not in event:
                continue
            items_to_render.append((i, event, None))

    rendered: List[Path] = []
    for i, event, frame in items_to_render:
        type_name = event.get("type", {}).get("name", "").lower()
        if type_filter and type_name not in type_filter:
            continue

        frame_path = output_dir / f"{i:05d}_{event['id'][:8]}.png"
        render_frame(event, frame, frame_path)
        rendered.append(frame_path)
        print(f"  rendered {len(rendered):4d}: {frame_path.name}")

        if args.limit and len(rendered) >= args.limit:
            break

    print(f"\nRendered {len(rendered)} frames to {output_dir.resolve()}")

    if not args.no_video and rendered:
        video_path = output_dir / args.video
        build_video(rendered, video_path, fps=args.fps)


if __name__ == "__main__":
    main()
