"""SAYA: an accessible, shade-aware walking route for one summer trip in Astana.

    python main.py                                   # hot day, wheelchair user
    python main.py --date 2026-08-20 --time 16:00    # a cool summer day
    python main.py --profile standard --time 18:00
    python main.py --feels-like 33                   # skip the weather API, use your own reading

Pipeline (each step feeds the next):
  1. A* search      builds two accessible routes: shortest and shaded
  2. Bayes          turns the weather reading into P(dangerous heat)
  3. MDP            uses both routes + P(dangerous heat) to choose one
"""

import argparse
import math
from datetime import datetime
from pathlib import Path

import bayes
import config
import mdp
import osm_data
import planner
import weather
from map_view import build_map
from sun import compass

LINE = "-" * 78


def header(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=config.DEFAULT_DATE, help="YYYY-MM-DD (default: %(default)s)")
    parser.add_argument("--time", default=config.DEFAULT_TIME, help="HH:MM Astana time (default: %(default)s)")
    parser.add_argument("--profile", default="wheelchair", choices=config.PROFILES)
    parser.add_argument("--start", default=config.DEFAULT_START, choices=config.PLACES)
    parser.add_argument("--end", default=config.DEFAULT_END, choices=config.PLACES)
    parser.add_argument("--feels-like", type=float, help="use this feels-like degC instead of Open-Meteo")
    parser.add_argument("--refresh-osm", action="store_true", help="download OpenStreetMap data again")
    parser.add_argument("--map", default="output/route_map.html", help="where to save the HTML map")
    parser.add_argument("--no-map", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    when = datetime.fromisoformat(f"{args.date}T{args.time}").replace(tzinfo=config.ASTANA_TZ)
    profile = config.PROFILES[args.profile]
    start, end = config.PLACES[args.start], config.PLACES[args.end]

    print("SAYA: accessible, shade-aware walking routes (Astana, EXPO district)")
    print(f"Trip: {start[0]} -> {end[0]} | {when:%Y-%m-%d %H:%M} (UTC+5) | {profile['label']}")

    # ------------------------------------------------------------ 0. data, sun, shade
    header("0. Map data, sun position and shade")
    graph, buildings, trees, barriers = osm_data.load_area(refresh=args.refresh_osm)
    network = planner.prepare_network(graph, buildings, trees, barriers, when)
    print(f"OpenStreetMap: {len(graph)} walk nodes, {graph.number_of_edges()} edges, "
          f"{len(buildings)} buildings, {len(trees)} trees / tree rows")
    if network.altitude > 0:
        ten_m = 10 / math.tan(math.radians(network.altitude))
        print(f"Sun: altitude {network.altitude:.1f} deg, azimuth {network.azimuth:.0f} deg "
              f"({compass(network.azimuth)}) -> a 10 m building casts a {ten_m:.1f} m shadow "
              f"towards {compass(network.azimuth + 180)}")
    else:
        print(f"Sun is below the horizon (altitude {network.altitude:.1f} deg): everything is in shade")
    print(f"Shade covers {network.shaded_share:.0%} of all path length at this time")
    for report in network.barriers:
        rule = profile["barrier"].get(report["type"], 1.0)
        effect = "impassable" if rule is None else f"cost x{rule:g}"
        print(f"Barrier report #{report['id']}: {report['name']} [{report['type']}] "
              f"-> {report['edges_marked']} edges, {effect} for this profile")

    # ------------------------------------------------------------ 1. A*
    header("1. A* search: two accessible routes")
    start_node = planner.nearest_node(network.graph, start[1], start[2])
    goal_node = planner.nearest_node(network.graph, end[1], end[2])
    print(f"Input: start node {start_node}, goal node {goal_node}, profile '{args.profile}'")
    print("Edge cost = length x access penalty x (1 + w x sun_fraction) + crossing penalty")
    print("Heuristic h(n) = straight-line distance to the goal (admissible: no edge costs less than its length)")
    routes = planner.plan_routes(network, start_node, goal_node, profile)
    print(f"\n{'route':9}{'w':>4}{'length':>9}{'in sun':>8}{'minutes':>9}{'sun min':>9}"
          f"{'A* expanded':>13}{'Dijkstra':>10}")
    for action, route in routes.items():
        s = route["stats"]
        print(f"{action:9}{s['sun_weight']:>4g}{s['length_m']:>7.0f} m{s['sun_share']:>8.0%}"
              f"{s['walk_min']:>9.1f}{s['sun_min']:>9.1f}{s['expanded']:>13}{s['dijkstra_expanded']:>10}")
    short, shaded = routes["Shortest"]["stats"], routes["Shaded"]["stats"]
    print(f"\nOutput: the shaded route is {shaded['length_m'] - short['length_m']:+.0f} m and "
          f"{shaded['walk_min'] - short['walk_min']:+.1f} min, with "
          f"{short['sun_m'] - shaded['sun_m']:.0f} m less walking in the sun.")
    print("Why A*: it finds the cheapest path like Dijkstra, but the distance heuristic makes it "
          "expand far fewer nodes.")

    # ------------------------------------------------------------ 2. Bayes
    header("2. Bayesian inference: is it dangerously hot?")
    if args.feels_like is not None:
        feels_like, source = args.feels_like, "entered by hand (--feels-like)"
    else:
        try:
            feels_like, source = weather.feels_like_at(when, start[1], start[2])
        except Exception as error:
            raise SystemExit(f"Weather lookup failed ({error}). Rerun with --feels-like <degC>.")
    reading = bayes.reading_bucket(feels_like)
    prior = bayes.prior_for_month(when.month)
    b = bayes.heat_posterior(prior, reading)
    print(f"Input: prior P(Dangerous) for month {when.month} = {prior:.2f}")
    print(f"       sensor = {source} -> reading '{reading}'")
    print(f"P({reading} | Dangerous) = {b['p_reading_given_dangerous']:.2f}, "
          f"P({reading} | Safe) = {b['p_reading_given_safe']:.2f}")
    print(f"P({reading}) = {prior:.2f} x {b['p_reading_given_dangerous']:.2f} + {1 - prior:.2f} x "
          f"{b['p_reading_given_safe']:.2f} = {b['evidence']:.3f}")
    print(f"P(Dangerous | {reading}) = {b['joint_dangerous']:.3f} / {b['evidence']:.3f} = {b['posterior']:.3f}")
    print(f"Output: P(dangerous heat) = {b['posterior']:.0%} (was {prior:.0%} before the reading).")
    print("Why Bayes: the forecast is a noisy sensor, so we combine it with what we knew before "
          "instead of trusting a single threshold.")

    # ------------------------------------------------------------ 3. MDP
    header("3. MDP: Shortest or Shaded?")
    stats = {a: routes[a]["stats"] for a in mdp.ACTIONS}
    transitions, rewards = mdp.build_model(stats, b["posterior"], profile["heat_vulnerability"])
    values = mdp.terminal_values()
    q, new_values, policy = mdp.bellman_update(transitions, rewards, values)
    print(f"Input: states {mdp.STATES}, actions {mdp.ACTIONS}, gamma = {config.MDP_GAMMA}")
    print(f"       P(Dangerous) = {b['posterior']:.3f}, heat vulnerability x{profile['heat_vulnerability']}, "
          f"V0 = {values}")
    print(f"\n{'s, a':28}{'P(->Comf.)':>11}{'P(->Stress)':>12}{'R':>8}{'Q(s,a)':>9}")
    for state in mdp.STATES:
        for action in mdp.ACTIONS:
            t = transitions[(state, action)]
            print(f"{state + ', ' + action:28}{t['Comfortable']:>11.3f}{t['HeatStressed']:>12.3f}"
                  f"{rewards[(state, action)]:>8.1f}{q[(state, action)]:>9.2f}")
    decision = policy["Comfortable"]
    other = "Shaded" if decision == "Shortest" else "Shortest"
    c = transitions[("Comfortable", decision)]
    print(f"\nQ(s,a) = R + gamma x [P(->Comf.) x 0 + P(->Stress) x {values['HeatStressed']:g}]")
    print(f"Output: start Comfortable -> choose {decision.upper()} "
          f"(Q = {q[('Comfortable', decision)]:.2f} vs {q[('Comfortable', other)]:.2f}).")
    print("Why MDP: it weighs a sure cost (extra minutes) against an uncertain one "
          "(heat stress) and picks the action with the best expected value.")

    # ------------------------------------------------------------ result + map
    chosen = routes[decision]["stats"]
    header("Recommendation")
    print(f"Take the {decision.lower()} route: {chosen['length_m']:.0f} m, about {chosen['walk_min']:.0f} min, "
          f"{chosen['sun_share']:.0%} in the sun, {c['HeatStressed']:.0%} chance of heat stress.")
    if chosen["barriers"]:
        print("Warning, passes reported barriers: " + "; ".join(chosen["barriers"]))
    if not args.no_map:
        summary = [
            f"{start[0]} &rarr; {end[0]}",
            f"{when:%d %b %Y, %H:%M} &middot; {profile['label']}",
            f"Sun {network.altitude:.0f}&deg; {compass(network.azimuth)} &middot; feels like {feels_like:.1f} &deg;C",
            f"P(dangerous heat) = {b['posterior']:.0%}",
            f"<b>Recommended: {decision}</b> &middot; {chosen['length_m']:.0f} m &middot; "
            f"{chosen['walk_min']:.0f} min &middot; {chosen['sun_share']:.0%} sun",
        ]
        path = build_map(graph, network, buildings, trees, routes, decision, summary, start, end,
                         Path(__file__).parent / args.map)
        print(f"Map saved to {path}")


if __name__ == "__main__":
    main()
