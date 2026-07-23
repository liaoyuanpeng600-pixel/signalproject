"""Tests for shared rendering utilities (Phase 6 Checkpoint 1)."""

import pytest

from src.reports.utils import (
    BANNED_PHRASES,
    LENGTH_CAPS,
    check_length_cap,
    find_banned_phrases,
    find_citations,
    format_citation,
    total_word_count,
)


# ----------------------- citations -----------------------


class TestCitations:
    def test_finds_single_citation(self) -> None:
        text = "ACME rose [sig:abc123]."
        assert find_citations(text) == ("[sig:abc123]",)

    def test_finds_multiple_citations(self) -> None:
        text = "[sig:a] and [thesis:b]"
        assert find_citations(text) == ("[sig:a]", "[thesis:b]")

    def test_deduplicates(self) -> None:
        text = "[sig:a] again [sig:a]"
        assert find_citations(text) == ("[sig:a]",)

    def test_no_citations(self) -> None:
        assert find_citations("plain text") == ()

    def test_format_citation(self) -> None:
        assert format_citation("sig", "abc") == "[sig:abc]"
        assert format_citation("thesis", "xyz") == "[thesis:xyz]"

    def test_format_citation_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValueError):
            format_citation("entity", "abc")


# ----------------------- length caps -----------------------


class TestLengthCaps:
    def test_headline_cap_is_100(self) -> None:
        assert LENGTH_CAPS["headline"] == 100

    def test_summary_cap_is_280(self) -> None:
        assert LENGTH_CAPS["summary"] == 280

    def test_within_cap(self) -> None:
        assert check_length_cap("short", "headline") is True

    def test_at_cap(self) -> None:
        text = "x" * 100
        assert check_length_cap(text, "headline") is True

    def test_over_cap(self) -> None:
        text = "x" * 101
        assert check_length_cap(text, "headline") is False

    def test_unknown_kind_falls_back_to_body(self) -> None:
        # Body cap is 5000 chars.
        assert check_length_cap("x" * 4999, "unknown_kind") is True
        assert check_length_cap("x" * 5001, "unknown_kind") is False


# ----------------------- banned phrases -----------------------


class TestBannedPhrases:
    def test_detects_known_banned(self) -> None:
        assert "we recommend" in find_banned_phrases("We recommend buying.")

    def test_case_insensitive(self) -> None:
        assert "moon" in find_banned_phrases("going to the MOON")

    def test_no_banned(self) -> None:
        assert find_banned_phrases("ACME reported EPS +14% vs consensus.") == ()

    def test_banned_list_nonempty(self) -> None:
        assert len(BANNED_PHRASES) > 0


# ----------------------- word count -----------------------


class TestWordCount:
    def test_total_word_count(self) -> None:
        assert total_word_count("one two three", "four") == 4

    def test_empty(self) -> None:
        assert total_word_count() == 0