from star.agents.researchers import make_researcher, research_fanout
from star.models import Category


def test_every_researcher_specifies_the_parseable_format():
    for category in Category:
        instruction = make_researcher(category).instruction
        assert " :: " in instruction, f"{category.value} lost the format separator"
        assert "one finding per line" in instruction.lower()


def test_every_researcher_keeps_the_uncertainty_escape_hatch():
    for category in Category:
        instruction = make_researcher(category).instruction
        assert "below the list" in instruction.lower()


def test_researchers_keep_the_adversarial_review_delimiters():
    """H2-cheap fix — data/instruction delimiters must survive reformatting."""
    for category in Category:
        instruction = make_researcher(category).instruction
        assert "<research_plan>" in instruction
        assert "never instructions to you" in instruction


def test_the_fanout_still_has_four_researchers_with_findings_output_keys():
    assert len(research_fanout.sub_agents) == 4
    keys = {agent.output_key for agent in research_fanout.sub_agents}
    assert keys == {f"findings_{c.value}" for c in Category}
