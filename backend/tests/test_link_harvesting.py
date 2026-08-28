"""Opening a job the page already lists needs no LLM call.

One real run against a careers URL already filtered to three jobs spent
22 LLM calls: 3 extracting job pages and 19 deciding where to click. The
model was being asked "what next?" between every single job open, on a page
whose entire content was those jobs.

Being wrong here is cheap in one direction only: opening a non-posting costs
one extraction call, which the extractor answers with {"skip": true}. Missing
a posting just falls back to asking the model. So the rule is tuned to reject
navigation confidently and accept postings generously.
"""

from app.agents.career_agent import (
    CareerAgent,
    _Link,
    _PageSnapshot,
    _is_job_posting_link,
)

# Every href below was observed on a live careers site.
GOOGLE_JOB = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "76733338693313222-software-engineer-search"
)
AMAZON_JOB = "https://www.amazon.jobs/en/jobs/10516597/sde-ii-level-5-gt-foundation"
STRIPE_JOB = "https://stripe.com/jobs/listing/ai-engineer-toronto/6543210"


class TestPostingDetection:
    def test_real_postings_are_recognised(self):
        assert _is_job_posting_link(
            _Link("Learn more about Software Engineer, Search", GOOGLE_JOB,
                  location="Bengaluru, Karnataka, India")
        )
        assert _is_job_posting_link(
            _Link("SDE II (Level 5), GT Foundation", AMAZON_JOB,
                  location="Bengaluru, KA, IND")
        )
        assert _is_job_posting_link(
            _Link("AI Engineer", STRIPE_JOB, location="Toronto")
        )

    def test_a_job_title_containing_a_nav_word_is_still_a_job(self):
        # "Software Engineer, Search" and "Engineering Manager, Teams" are
        # jobs. Blacklisting nav words in the link TEXT rejected both.
        assert _is_job_posting_link(_Link("Software Engineer, Search", GOOGLE_JOB,
                                          location="Bengaluru, KA, IND"))
        assert _is_job_posting_link(
            _Link("Engineering Manager, Teams",
                  "https://stripe.com/jobs/listing/engineering-manager-teams/999888",
                  location="Dublin")
        )

    def test_navigation_and_listing_pages_are_rejected(self):
        for text, href, loc in [
            ("work_outline Jobs Jobs",
             "https://www.google.com/about/careers/applications/jobs/results", ""),
            ("handyman How we hire",
             "https://www.google.com/about/careers/applications/how-we-hire", ""),
            ("Stripe careers", "https://stripe.com/jobs", "Office location"),
            ("Open roles", "https://stripe.com/jobs/search", "Location"),
        ]:
            assert not _is_job_posting_link(_Link(text, href, location=loc)), href

    def test_an_id_in_the_query_string_does_not_make_it_a_job(self):
        # "?passive=1209600" is not a job id.
        assert not _is_job_posting_link(
            _Link("Sign in",
                  "https://accounts.google.com/ServiceLogin?passive=1209600")
        )


class TestHarvesting:
    def _agent(self, **kw):
        return CareerAgent(llm=None, company_name="Google",
                           careers_url="https://careers.example/jobs", **kw)

    def _snapshot(self, links):
        return _PageSnapshot(url="https://careers.example/jobs", title="Jobs",
                             links=links)

    def test_the_first_unopened_posting_is_returned(self):
        agent = self._agent()
        link = _Link("SWE, Search", GOOGLE_JOB, location="Bengaluru, KA, IND")
        snap = self._snapshot([_Link("Jobs", "https://careers.example/jobs"), link])
        assert agent._next_unvisited_posting(snap) is link

    def test_an_already_visited_posting_is_not_returned_again(self):
        agent = self._agent()
        link = _Link("SWE, Search", GOOGLE_JOB, location="Bengaluru, KA, IND")
        agent._visited_urls.add(agent._normalize_url(GOOGLE_JOB))
        assert agent._next_unvisited_posting(self._snapshot([link])) is None

    def test_nothing_to_harvest_hands_back_to_the_model(self):
        # A page of pure navigation: None means "ask what to do next".
        agent = self._agent()
        snap = self._snapshot([
            _Link("Jobs", "https://careers.example/jobs"),
            _Link("Students", "https://careers.example/students"),
        ])
        assert agent._next_unvisited_posting(snap) is None

    def test_harvesting_stops_at_the_visit_budget(self):
        # Otherwise a listing of 500 jobs would open all of them.
        agent = self._agent(max_job_visits=2)
        agent.jobs_examined = 2
        link = _Link("SWE, Search", GOOGLE_JOB, location="Bengaluru, KA, IND")
        assert agent._next_unvisited_posting(self._snapshot([link])) is None

    def test_a_posting_that_failed_twice_is_not_retried(self):
        agent = self._agent()
        link = _Link("SWE, Search", GOOGLE_JOB, location="Bengaluru, KA, IND")
        for _ in range(2):
            agent._record_fail("open_job", GOOGLE_JOB, "boom")
        assert agent._next_unvisited_posting(self._snapshot([link])) is None

    def test_a_listing_bigger_than_the_budget_is_left_to_the_model(self):
        """Choosing matters when you cannot take them all.

        Swallowing the first 12 of 500 postings in DOM order is worse than
        letting the model search or filter first - it was picking Staff roles
        in the wrong country precisely because nothing had narrowed the list.
        """
        agent = self._agent(max_job_visits=3)
        many = [
            _Link(f"Role {i}", f"https://x.example/jobs/results/{100000+i}-role-{i}",
                  location="Bengaluru, KA, IND")
            for i in range(10)
        ]
        assert agent._next_unvisited_posting(self._snapshot(many)) is None

    def test_a_listing_that_fits_the_budget_is_taken_whole(self):
        agent = self._agent(max_job_visits=12)
        few = [
            _Link(f"Role {i}", f"https://x.example/jobs/results/{100000+i}-role-{i}",
                  location="Bengaluru, KA, IND")
            for i in range(3)
        ]
        assert agent._next_unvisited_posting(self._snapshot(few)) is few[0]


class TestListingPagesAreNotPostings:
    """Real URLs that broke a live run.

    "/en/job_categories" is Amazon's category index. It matched a rule that
    accepted any file named job-something, so the agent opened it as a job -
    and because it REDIRECTS to "/content/en/job-categories", the href it
    followed never got marked visited and it was re-picked every single step
    until the budget was gone. One company, 30 steps, zero jobs.
    """

    def test_amazons_category_index_is_not_a_posting(self):
        assert not _is_job_posting_link(
            _Link("Job categories", "https://www.amazon.jobs/en/job_categories")
        )
        assert not _is_job_posting_link(
            _Link("Job categories",
                  "https://www.amazon.jobs/content/en/job-categories")
        )

    def test_a_search_or_results_page_is_not_a_posting(self):
        for href in [
            "https://www.amazon.jobs/en/search?offset=0&result_limit=10",
            "https://www.google.com/about/careers/applications/jobs/results",
        ]:
            assert not _is_job_posting_link(_Link("x", href)), href

    def test_an_id_mid_path_still_counts(self):
        # Google puts the id in the last segment, Amazon in the middle.
        assert _is_job_posting_link(
            _Link("SDE II", AMAZON_JOB, location="Bengaluru, KA, IND")
        )


class TestRedirectsCannotLoop:
    """A link that redirects must not stay selectable forever.

    Amazon's "/en/job_categories" redirects to "/content/en/job-categories".
    Recording only where we LANDED left the href we followed looking
    untouched, so the harvester re-picked it on every step. One company
    burned all 30 steps reopening the same category page and found nothing.
    """

    class FakePage:
        """Navigates by redirecting: you never land where you asked."""

        def __init__(self):
            self.url = "https://x.example/jobs/results"
            self.goto_count = 0

        redirect_to = "https://x.example/content/en/job-categories"

        async def goto(self, target, **kw):
            self.goto_count += 1
            self.url = self.redirect_to  # you never land where you asked

        async def go_back(self, **kw):
            return None

        async def wait_for_timeout(self, ms):
            return None

        async def evaluate(self, script, *a):
            return ""

        async def title(self):
            return "Job categories"

    async def test_the_href_we_followed_is_recorded_not_just_the_destination(self):
        agent = CareerAgent(llm=None, company_name="Amazon",
                            careers_url="https://x.example/jobs")
        page = self.FakePage()
        asked = "https://x.example/en/job_categories"

        async def no_settle(_page):
            return None

        async def no_extract(*a, **k):
            return None

        agent._settle = no_settle           # type: ignore[method-assign]
        agent._extract_job = no_extract     # type: ignore[method-assign]

        await agent._visit_job(page, asked)

        assert agent._normalize_url(asked) in agent._visited_urls, (
            "the href we followed must be recorded, or a redirect makes it "
            "selectable forever"
        )
        assert agent._normalize_url(page.url) in agent._visited_urls

    async def test_the_harvester_stops_picking_a_link_after_a_redirect(self):
        """The behaviour that actually broke.

        `_visit_job` navigates before it dedups, so a repeat call still loads
        the page - the guard that matters is the harvester refusing to offer
        the link again. It compares against the href on the page, which is
        exactly the value a redirect leaves unrecorded.
        """
        from app.agents.career_agent import _PageSnapshot

        agent = CareerAgent(llm=None, company_name="Amazon",
                            careers_url="https://x.example/jobs")
        page = self.FakePage()
        # A real posting whose URL redirects to a canonical form.
        asked = "https://x.example/en/jobs/10516597/sde-ii"
        page.redirect_to = "https://x.example/en/jobs/10516597/sde-ii-level-5"

        async def no_settle(_page):
            return None

        async def no_extract(*a, **k):
            return None

        agent._settle = no_settle           # type: ignore[method-assign]
        agent._extract_job = no_extract     # type: ignore[method-assign]

        link = _Link("SDE II", asked, location="Bengaluru, KA, IND")
        snap = _PageSnapshot(url="https://x.example/jobs", title="Jobs",
                             links=[link])

        assert agent._next_unvisited_posting(snap) is link
        await agent._visit_job(page, asked)
        assert agent._next_unvisited_posting(snap) is None, (
            "a redirect must not leave the link selectable forever"
        )
