"""MDP: take the shortest route or the shaded one?

States  S = {Comfortable, HeatStressed}   (the walker's condition)
Actions A = {Shortest, Shaded}             (the two A* routes)

Transitions come from the routes and from the Bayes belief about the heat:
every minute in direct sun is a small chance of becoming heat-stressed, and
that chance is much larger when the heat is Dangerous. Shade helps a stressed
walker recover.

Reward R(s, a) = -(walking minutes of route a).
Terminal values V0(Comfortable) = 0, V0(HeatStressed) = -HEAT_STRESS_PENALTY.

One Bellman update:  Q(s, a) = R(s, a) + gamma * sum_s' P(s' | s, a) * V0(s')
The recommended action is argmax_a Q(Comfortable, a).
"""

import config

STATES = ("Comfortable", "HeatStressed")
ACTIONS = ("Shortest", "Shaded")


def p_heat_stress(sun_minutes: float, p_dangerous: float, vulnerability: float) -> float:
    """Expected chance of getting heat-stressed, averaged over the Bayes belief about the weather."""
    total = 0.0
    for weather, p_weather in (("Dangerous", p_dangerous), ("Safe", 1 - p_dangerous)):
        hazard = min(vulnerability * config.HAZARD_PER_SUN_MINUTE[weather], 0.99)
        total += p_weather * (1 - (1 - hazard) ** sun_minutes)
    return total


def build_model(routes: dict, p_dangerous: float, vulnerability: float):
    """routes: {"Shortest": stats, "Shaded": stats} from search.route_stats."""
    transitions, rewards = {}, {}
    for action in ACTIONS:
        stats = routes[action]
        p_stress = p_heat_stress(stats["sun_min"], p_dangerous, vulnerability)
        p_recover = config.RECOVERY_IN_SHADE * (1 - stats["sun_share"])
        transitions[("Comfortable", action)] = {"Comfortable": 1 - p_stress, "HeatStressed": p_stress}
        transitions[("HeatStressed", action)] = {"Comfortable": p_recover, "HeatStressed": 1 - p_recover}
        for state in STATES:
            rewards[(state, action)] = -stats["walk_min"]
    return transitions, rewards


def terminal_values() -> dict:
    return {"Comfortable": 0.0, "HeatStressed": -config.HEAT_STRESS_PENALTY}


def bellman_update(transitions, rewards, values, gamma=config.MDP_GAMMA):
    """One Bellman backup. Returns Q table, new state values and the greedy policy."""
    q = {}
    for state in STATES:
        for action in ACTIONS:
            future = sum(p * values[nxt] for nxt, p in transitions[(state, action)].items())
            q[(state, action)] = rewards[(state, action)] + gamma * future
    new_values = {s: max(q[(s, a)] for a in ACTIONS) for s in STATES}
    policy = {s: max(ACTIONS, key=lambda a: q[(s, a)]) for s in STATES}
    return q, new_values, policy
