from app.analysis import scoring, tagger


def test_what_counts_is_how_the_probability_moved_and_for_whom():
    cases = scoring.market_cases()
    plain = {(c.yes_is_good, c.change): c.contribution for c in cases if not c.deadline}
    assert plain[(True, 0.10)] == 1.0  # good news became likelier
    assert plain[(True, -0.10)] == -1.0  # good news became less likely
    assert plain[(False, 0.10)] == -1.0  # bad news became likelier
    assert plain[(False, -0.10)] == 1.0  # bad news became less likely: good for the ticker


def test_a_deadline_market_only_counts_what_the_clock_doesnt_explain():
    falls = [c for c in scoring.market_cases() if c.deadline]
    bigger, smaller = falls
    # A fall of 6 points, of which the day passing explains about 4.
    assert 0 < bigger.contribution < 0.3
    # A fall of 3 points, all explained by the clock: it isn't news.
    assert smaller.contribution == 0.0


def test_the_prompt_shown_is_the_one_sent():
    shown = tagger.prompt_for_display()
    assert tagger.SYSTEM.split("{tickers}")[0] in shown
    assert "direction refers to the YES outcome" in shown
    assert "{" not in shown
