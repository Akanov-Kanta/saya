"""Bayesian inference: how likely is it that walking now means dangerous heat?

Hidden state H in {Dangerous, Safe}. We never observe it directly. We observe
a noisy sensor reading: the forecast "feels like" temperature, put into a
bucket (cool / warm / hot). Bayes' rule turns the prior into a posterior:

    P(Dangerous | reading) = P(reading | Dangerous) * P(Dangerous) / P(reading)
    P(reading) = P(reading | Dangerous) P(Dangerous) + P(reading | Safe) P(Safe)
"""

import config


def prior_for_month(month: int) -> float:
    return config.HEAT_PRIOR_BY_MONTH.get(month, config.HEAT_PRIOR_DEFAULT)


def reading_bucket(feels_like_c: float) -> str:
    for upper, name in config.FEELS_LIKE_BUCKETS:
        if feels_like_c < upper:
            return name
    return config.FEELS_LIKE_BUCKETS[-1][1]


def heat_posterior(prior: float, reading: str, likelihood=config.HEAT_LIKELIHOOD) -> dict:
    """One Bayes update with one observation. Returns every intermediate number for printing."""
    p_reading_given_d = likelihood["Dangerous"][reading]
    p_reading_given_s = likelihood["Safe"][reading]
    joint_d = prior * p_reading_given_d            # P(reading, Dangerous)
    joint_s = (1 - prior) * p_reading_given_s      # P(reading, Safe)
    evidence = joint_d + joint_s                   # P(reading)
    return {
        "prior": prior,
        "reading": reading,
        "p_reading_given_dangerous": p_reading_given_d,
        "p_reading_given_safe": p_reading_given_s,
        "joint_dangerous": joint_d,
        "joint_safe": joint_s,
        "evidence": evidence,
        "posterior": joint_d / evidence,
    }
