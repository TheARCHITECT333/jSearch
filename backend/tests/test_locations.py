"""Location matching tests: aliases, remote handling, unknown locations.

Philosophy matches freshness: jobs are only dropped when their stated
location CLEARLY falls outside every requested location. Unknown stays.
"""

from __future__ import annotations

from app.schemas import DiscoveredJob
from app.services.locations import (
    filter_jobs_by_location,
    location_matches,
)

WANTED = ["Bangalore", "Remote"]


def job(location: str | None, url: str | None = None) -> DiscoveredJob:
    path = url or f"jobs/{abs(hash(str(location))) % 100000}"
    if not path.startswith("http"):
        path = f"https://x.example/{path}"
    return DiscoveredJob(title="Engineer", url=path, location=location)


class TestLocationMatches:
    def test_no_wanted_locations_keeps_everything(self):
        assert location_matches("San Francisco", []) is True
        assert location_matches(None, []) is True

    def test_unknown_job_location_is_kept(self):
        assert location_matches(None, WANTED) is True
        assert location_matches("", WANTED) is True
        assert location_matches("   ", WANTED) is True

    def test_exact_and_partial_city_match(self):
        assert location_matches("Bangalore, India", WANTED)
        assert location_matches("Bangalore Urban", ["bangalore"])
        assert location_matches("Remote - Worldwide", WANTED)

    def test_alias_bengaluru_matches_bangalore(self):
        assert location_matches("Bengaluru, Karnataka", ["Bangalore"])

    def test_case_insensitive(self):
        assert location_matches("BANGALORE", ["bangaLORE"])

    def test_clear_mismatch_dropped(self):
        assert not location_matches("San Francisco, CA", WANTED)
        assert not location_matches("London, UK", ["New York"])
        assert not location_matches("Tokyo", ["Singapore", "Dubai"])

    def test_remote_job_fits_any_selection(self):
        assert location_matches("Remote", ["New York"])
        assert location_matches("Work from home (India)", ["Bangalore"])
        assert location_matches("Anywhere", ["Berlin"])

    def test_remote_only_request_rejects_city_jobs(self):
        assert not location_matches("Pune, India", ["Remote"])
        assert location_matches("Hybrid - Remote in Bangalore", ["Remote"])
        # A pure city posting is NOT remote-only compatible...
        assert not location_matches("Bangalore", ["remote"])

    def test_multi_location_any_match_passes(self):
        assert location_matches("Mumbai", ["Delhi", "Mumbai"])
        assert not location_matches("Chennai", ["Delhi", "Mumbai"])

    def test_country_level_selection(self):
        assert location_matches("Bangalore, India", ["India"])
        assert location_matches("Austin, TX", ["United States"]) is False  # country name not printed


class TestFilterJobsByLocation:
    def test_split(self):
        jobs = [
            job("Bangalore", url="u-in"),
            job("San Francisco", url="u-out"),
            job(None, url="u-unknown"),
            job("Remote", url="u-remote"),
        ]
        kept, dropped = filter_jobs_by_location(jobs, WANTED)
        assert [j.url.rsplit("/", 1)[-1] for j in kept] == [
            "u-in",
            "u-unknown",
            "u-remote",
        ]
        assert [j.url.rsplit("/", 1)[-1] for j in dropped] == ["u-out"]

    def test_empty_wanted_returns_all(self):
        jobs = [job("X"), job("Y")]
        kept, dropped = filter_jobs_by_location(jobs, [])
        assert len(kept) == 2 and dropped == []


class TestListingPrefilter:
    """Drop foreign listings BEFORE opening them, not after extracting them.

    A search restricted to India examined 8 Google jobs and discarded 7 as
    "outside [India]" - each one having already cost a page load and an LLM
    extraction. The links were opened blind because a listing row states its
    location beside the anchor, never inside it.
    """

    def _agent(self, locations):
        from app.agents.career_agent import CareerAgent

        return CareerAgent(
            llm=None,
            company_name="Google",
            careers_url="https://careers.example/jobs",
            locations=locations,
        )

    def _links(self, pairs):
        from app.agents.career_agent import _Link

        # Posting-shaped hrefs on purpose: the location filter applies only
        # to individual postings, never to navigation.
        return [
            _Link(
                text=t,
                href=f"https://careers.example/jobs/results/{100000 + i}-a-role",
                location=loc,
            )
            for i, (t, loc) in enumerate(pairs)
        ]

    def test_a_listing_shown_elsewhere_is_never_opened(self):
        agent = self._agent(["India"])
        kept = agent._drop_foreign_links(
            self._links(
                [
                    ("Software Engineer, Search", "Bengaluru, Karnataka, India"),
                    ("Software Engineer, Core", "Mountain View, CA, USA"),
                    ("Software Engineer, Ads", "Warsaw, Poland"),
                ]
            )
        )
        assert [lnk.text for lnk in kept] == ["Software Engineer, Search"]

    def test_a_listing_with_no_stated_location_is_kept(self):
        # Same rule as the post-extraction filter: never guess. An unlabelled
        # listing might well be the one you want.
        agent = self._agent(["India"])
        kept = agent._drop_foreign_links(self._links([("Software Engineer", "")]))
        assert len(kept) == 1

    def test_remote_listings_survive_a_city_search(self):
        agent = self._agent(["India"])
        kept = agent._drop_foreign_links(
            self._links([("Backend Engineer", "Remote")])
        )
        assert len(kept) == 1

    def test_nothing_is_dropped_when_no_location_was_requested(self):
        agent = self._agent([])
        kept = agent._drop_foreign_links(
            self._links([("SWE", "Mountain View, CA, USA"), ("SWE2", "Tokyo, Japan")])
        )
        assert len(kept) == 2

    def test_city_aliases_still_apply(self):
        # Searching "Bangalore" must keep a listing printed as "Bengaluru".
        agent = self._agent(["Bangalore"])
        kept = agent._drop_foreign_links(
            self._links([("SWE", "Bengaluru, Karnataka, India")])
        )
        assert len(kept) == 1

    def test_navigation_links_are_never_filtered_by_location(self):
        """Sites label their location FILTER "Location" too.

        Stripe's careers nav picks up loc="Office location"; filtering that
        against ["India"] would drop the link and strand the agent on a page
        it can no longer navigate away from.
        """
        from app.agents.career_agent import _Link

        agent = self._agent(["India"])
        nav = [
            _Link(text="Stripe careers", href="https://stripe.com/jobs",
                  location="Office location"),
            _Link(text="Open roles", href="https://stripe.com/jobs/search",
                  location="Location"),
        ]
        assert agent._drop_foreign_links(nav) == nav

class TestCountryCodes:
    """Boards print the country as an ISO code as often as they spell it out.

    Amazon renders "Bengaluru, KA, IND". A search for "India" found no whole
    word "india", so every one of the ten results on a page ALREADY filtered
    to India was discarded, and the company returned nothing.
    """

    def test_the_exact_string_that_broke_an_amazon_search(self):
        assert location_matches("Bengaluru, KA, IND | Job ID: 10516597", ["India"])

    def test_iso_code_matches_the_spelled_out_country(self):
        assert location_matches("Seattle, WA, USA", ["United States"])
        assert location_matches("Toronto, ON, CAN", ["Canada"])
        assert location_matches("Munich, BY, DEU", ["Germany"])

    def test_the_spelled_out_country_matches_an_iso_wanted_value(self):
        # Aliases are applied to both sides, so direction never matters.
        assert location_matches("Bengaluru, Karnataka, India", ["IND"])

    def test_a_different_country_still_does_not_match(self):
        assert not location_matches("Seattle, WA, USA", ["India"])
        assert not location_matches("Bengaluru, KA, IND", ["Germany"])

    def test_city_alias_and_country_code_compose(self):
        # "Bengaluru" -> "bangalore" and "IND" -> "india" in one string.
        assert location_matches("Bengaluru, KA, IND", ["Bangalore"])
        assert location_matches("Bengaluru, KA, IND", ["India"])

    def test_codes_that_are_ordinary_words_are_deliberately_absent(self):
        # "PER", "NOR" and "ARE" are real ISO codes and real English words.
        # Matching the wrong country is worse than missing an abbreviation.
        from app.services.locations import _COUNTRY_CODES

        assert not {"per", "nor", "are", "and", "can't"} & set(_COUNTRY_CODES) - {"can"}
