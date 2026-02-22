"""Tests for data models."""

from research_analyser.models import PeerReview


def test_compute_score():
    """Test the scoring formula: score = -0.3057 + 0.7134*S + 0.4242*P + 1.0588*C"""
    # All scores at maximum (4)
    score = PeerReview.compute_score(4.0, 4.0, 4.0)
    expected = -0.3057 + 0.7134 * 4 + 0.4242 * 4 + 1.0588 * 4
    assert abs(score - expected) < 0.001

    # All scores at minimum (1)
    score = PeerReview.compute_score(1.0, 1.0, 1.0)
    expected = -0.3057 + 0.7134 * 1 + 0.4242 * 1 + 1.0588 * 1
    assert abs(score - expected) < 0.001

    # Score should be clamped between 1 and 10
    assert 1.0 <= PeerReview.compute_score(1, 1, 1) <= 10.0
    assert 1.0 <= PeerReview.compute_score(4, 4, 4) <= 10.0


def test_compute_score_weights():
    """Contribution should have the highest impact on final score."""
    base = PeerReview.compute_score(2, 2, 2)

    # Increasing contribution by 1 should have the largest effect
    delta_s = PeerReview.compute_score(3, 2, 2) - base
    delta_p = PeerReview.compute_score(2, 3, 2) - base
    delta_c = PeerReview.compute_score(2, 2, 3) - base

    assert delta_c > delta_s > delta_p
