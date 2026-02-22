"""Tests for the reviewer scoring system."""

from research_analyser.reviewer import compute_final_score, interpret_score


def test_compute_final_score_formula():
    """Verify: score = -0.3057 + 0.7134*S + 0.4242*P + 1.0588*C"""
    score = compute_final_score(3.0, 3.0, 3.0)
    expected = -0.3057 + 0.7134 * 3 + 0.4242 * 3 + 1.0588 * 3
    assert abs(score - expected) < 0.001


def test_score_clamping():
    """Score should be clamped between 1 and 10."""
    assert compute_final_score(0, 0, 0) == 1.0
    assert compute_final_score(4, 4, 4) <= 10.0


def test_interpret_score():
    assert interpret_score(2.0) == "Strong Reject"
    assert interpret_score(3.5) == "Reject"
    assert interpret_score(4.5) == "Weak Reject"
    assert interpret_score(5.5) == "Borderline"
    assert interpret_score(6.5) == "Weak Accept"
    assert interpret_score(7.5) == "Accept"
    assert interpret_score(8.5) == "Strong Accept"


def test_contribution_has_highest_weight():
    """Contribution (weight 1.0588) should have the largest impact."""
    base = compute_final_score(2, 2, 2)
    delta_c = compute_final_score(2, 2, 3) - base
    delta_s = compute_final_score(3, 2, 2) - base
    delta_p = compute_final_score(2, 3, 2) - base

    assert abs(delta_c - 1.0588) < 0.001
    assert abs(delta_s - 0.7134) < 0.001
    assert abs(delta_p - 0.4242) < 0.001
    assert delta_c > delta_s > delta_p
