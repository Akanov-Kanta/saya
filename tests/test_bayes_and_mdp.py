import pytest

import bayes
import config
import mdp


def test_reading_buckets():
    assert bayes.reading_bucket(17.6) == "cool"
    assert bayes.reading_bucket(24.0) == "warm"
    assert bayes.reading_bucket(29.9) == "warm"
    assert bayes.reading_bucket(30.0) == "hot"


def test_hot_reading_raises_heat_probability():
    # P(D|hot) = 0.30*0.70 / (0.30*0.70 + 0.70*0.10) = 0.21 / 0.28 = 0.75
    result = bayes.heat_posterior(0.30, "hot")
    assert result["evidence"] == pytest.approx(0.28)
    assert result["posterior"] == pytest.approx(0.75)


def test_cool_reading_lowers_heat_probability():
    # P(D|cool) = 0.25*0.05 / (0.25*0.05 + 0.75*0.55) = 0.0125 / 0.425
    assert bayes.heat_posterior(0.25, "cool")["posterior"] == pytest.approx(0.0125 / 0.425)


# Route numbers from a real run (wheelchair user, AITU -> Mega Silk Way, 15 July 16:00)
ROUTES = {
    "Shortest": {"walk_min": 28.8, "sun_min": 28.8, "sun_share": 1.00},
    "Shaded":   {"walk_min": 30.6, "sun_min": 24.7, "sun_share": 0.81},
}


def decide(p_dangerous, vulnerability=1.5):
    transitions, rewards = mdp.build_model(ROUTES, p_dangerous, vulnerability)
    q, _, policy = mdp.bellman_update(transitions, rewards, mdp.terminal_values())
    return policy["Comfortable"], q, transitions, rewards


def test_transition_rows_sum_to_one():
    _, _, transitions, _ = decide(0.5)
    for row in transitions.values():
        assert sum(row.values()) == pytest.approx(1)


def test_dangerous_heat_chooses_shade_and_cool_weather_chooses_shortest():
    assert decide(0.75)[0] == "Shaded"
    assert decide(0.03)[0] == "Shortest"


def test_q_value_is_one_bellman_backup():
    _, q, transitions, rewards = decide(0.75)
    t = transitions[("Comfortable", "Shaded")]
    expected = rewards[("Comfortable", "Shaded")] + config.MDP_GAMMA * (
        t["Comfortable"] * 0 + t["HeatStressed"] * -config.HEAT_STRESS_PENALTY)
    assert q[("Comfortable", "Shaded")] == pytest.approx(expected)
