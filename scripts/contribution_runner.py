#!/usr/bin/env python3
"""Render a GitHub contribution graph as a tiny platformer.

A pixel runner sprints along the ground, jumps onto each week's top-most green
block, hops block to block when they are close, and pops a coin on every landing.

Usage: GITHUB_TOKEN=... python3 contribution_runner.py <user> <out_dir>
Writes <out_dir>/runner.svg and <out_dir>/runner-dark.svg.
"""
import json
import os
import sys
import urllib.request

CELL, GAP = 10, 3
PITCH = CELL + GAP
LEFT, TOP = 16, 40
SPEED = 110  # px/s while running on the ground
MAX_HOP = 4  # furthest column distance jumped directly from block to block
PAUSE = 1.2  # seconds off-screen before the loop restarts

THEMES = {
    "runner": {"levels": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"], "ground": "#d0d7de"},
    "runner-dark": {"levels": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"], "ground": "#30363d"},
}
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

# 8x11 sprite facing right; the last two rows are the legs, drawn in two frames.
PALETTE = {"H": "#5a3214", "R": "#e5534b", "S": "#f6c48e", "E": "#1f2328", "B": "#2f81f7", "P": "#6e40c9", "K": "#e5534b"}
BODY = ["..HHHH..", ".RRRRRRR", ".HSSSES.", ".SSSSSS.", "..SSSS..", ".BBBBBB.", "SBBBBBBS", "..BBBB..", "..PPPP.."]
LEGS_A = [".P....P.", "KK....KK"]
LEGS_B = ["...PP...", "...KK..."]


def fetch_weeks(user, token):
    query = "query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{weeks{contributionDays{weekday contributionLevel}}}}}}"
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"u": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [{d["weekday"]: LEVELS[d["contributionLevel"]] for d in w["contributionDays"]} for w in weeks]


class Motion:
    """Keyframes (time, x, y) for the runner's feet."""

    def __init__(self, x, y):
        self.t, self.x, self.y = 0.0, x, y
        self.frames = [(0.0, x, y)]

    def run(self, x):
        self.t += abs(x - self.x) / SPEED
        self.x = x
        self.frames.append((self.t, self.x, self.y))

    def jump(self, x, y, steps=12):
        x0, y0 = self.x, self.y
        dur = 0.32 + abs(x - x0) / 400
        h = 10 + abs(y - y0) * 0.5
        for i in range(1, steps + 1):
            u = i / steps
            self.frames.append((self.t + dur * u, x0 + (x - x0) * u, y0 + (y - y0) * u - 4 * h * u * (1 - u)))
        self.t += dur
        self.x, self.y = x, y

    def wait(self, dur):
        self.t += dur
        self.frames.append((self.t, self.x, self.y))


def plan(weeks, width, ground_y):
    targets = [(c, min(r for r, lvl in w.items() if lvl)) for c, w in enumerate(weeks) if any(w.values())]
    m = Motion(-12, ground_y)
    landings = []
    on_block = None
    for col, row in targets:
        x, y = LEFT + col * PITCH + CELL / 2, TOP + row * PITCH
        if on_block is not None and col - on_block > MAX_HOP:
            m.jump(m.x + PITCH * 1.5, ground_y)
            on_block = None
        if on_block is None:
            m.run(max(m.x, x - 2 * PITCH))
        m.jump(x, y)
        landings.append((m.t, col, row))
        m.wait(0.08)
        on_block = col
    if on_block is not None:
        m.jump(m.x + PITCH * 1.5, ground_y)
    m.run(width + 12)
    m.wait(PAUSE)
    return m, landings


def pct(t, total):
    return f"{min(max(t / total * 100, 0), 100):.3f}%"


def sprite_rects(rows, y_offset=0):
    out = []
    for y, line in enumerate(rows):
        x = 0
        while x < len(line):
            ch = line[x]
            if ch == ".":
                x += 1
                continue
            end = x
            while end < len(line) and line[end] == ch:
                end += 1
            out.append(f'<rect x="{x}" y="{y + y_offset}" width="{end - x}" height="1" fill="{PALETTE[ch]}"/>')
            x = end
    return "".join(out)


def render(weeks, theme):
    width = LEFT * 2 + len(weeks) * PITCH - GAP
    ground_y = TOP + 7 * PITCH + 2
    height = ground_y + 12
    m, landings = plan(weeks, width, ground_y)
    total = m.t

    css = ["@keyframes run{" + "".join(f"{pct(t, total)}{{transform:translate({x:.1f}px,{y:.1f}px)}}" for t, x, y in m.frames) + "}"]
    css.append(".runner{animation:run %.2fs linear infinite}" % total)
    css.append("@keyframes la{0%,50%{opacity:1}50.1%,100%{opacity:0}}@keyframes lb{0%,50%{opacity:0}50.1%,100%{opacity:1}}")
    css.append(".la{animation:la .24s linear infinite}.lb{animation:lb .24s linear infinite}")

    landed = {}
    for i, (t, col, row) in enumerate(landings):
        landed[(col, row)] = i
        css.append(
            f"@keyframes b{i}{{0%,{pct(t, total)},{pct(t + 0.2, total)},100%{{transform:translateY(0)}}{pct(t + 0.08, total)}{{transform:translateY(-3px)}}}}"
            f".b{i}{{animation:b{i} {total:.2f}s linear infinite}}"
            f"@keyframes c{i}{{0%,{pct(t - 0.01, total)}{{opacity:0;transform:translateY(0)}}{pct(t, total)}{{opacity:1;transform:translateY(0)}}"
            f"{pct(t + 0.55, total)},100%{{opacity:0;transform:translateY(-18px)}}}}"
            f".c{i}{{animation:c{i} {total:.2f}s ease-out infinite;opacity:0}}"
        )

    cells, coins = [], []
    for c, week in enumerate(weeks):
        for r, lvl in week.items():
            x, y = LEFT + c * PITCH, TOP + r * PITCH
            cls = f' class="b{landed[(c, r)]}"' if (c, r) in landed else ""
            cells.append(f'<rect{cls} x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{theme["levels"][lvl]}"/>')
            if (c, r) in landed:
                coins.append(f'<rect class="c{landed[(c, r)]}" x="{x + 3}" y="{y - 8}" width="4" height="6" rx="1" fill="#f2c94c" stroke="#b7791f" stroke-width=".6"/>')
    ground = "".join(
        f'<rect x="{x}" y="{ground_y + 1}" width="{CELL}" height="6" rx="1" fill="{theme["ground"]}"/>'
        for x in range(LEFT, width - LEFT, PITCH)
    )
    runner = (
        '<g class="runner"><g transform="translate(-5,-13.75) scale(1.25)" shape-rendering="crispEdges">'
        f"{sprite_rects(BODY)}"
        f'<g class="la">{sprite_rects(LEGS_A, len(BODY))}</g>'
        f'<g class="lb">{sprite_rects(LEGS_B, len(BODY))}</g>'
        "</g></g>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<style>{"".join(css)}</style>{ground}{"".join(cells)}{"".join(coins)}{runner}</svg>'
    )


def main():
    user, out_dir = sys.argv[1], sys.argv[2]
    weeks = fetch_weeks(user, os.environ["GITHUB_TOKEN"])
    os.makedirs(out_dir, exist_ok=True)
    for name, theme in THEMES.items():
        with open(os.path.join(out_dir, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(render(weeks, theme))


if __name__ == "__main__":
    main()
