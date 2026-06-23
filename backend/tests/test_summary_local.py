from deepreader.summarise.local import LocalExtractiveSummariser
from deepreader.summarise.summariser import SummaryInput


def test_local_summariser_is_deterministic_and_extracts_first_sentence() -> None:
    summariser = LocalExtractiveSummariser()
    item = SummaryInput(
        stable_id="doc_test/para_0001",
        source_text="  Alarm A18 indicates high motor current. The most common cause is bearing wear.  ",
        source_hash="abc123",
        metadata={},
    )

    first = summariser.summarise(item)
    second = summariser.summarise(item)

    assert first == second
    assert first.summariser_name == "local_extractive_v1"
    assert first.summary_text == "Alarm A18 indicates high motor current."
    assert first.summary_hash


def test_local_summariser_truncates_predictably() -> None:
    summariser = LocalExtractiveSummariser(max_chars=36)
    item = SummaryInput(
        stable_id="doc_test/para_0002",
        source_text="The filter cartridge contains repeated coolant residue and metal fines before service.",
        source_hash="def456",
        metadata={},
    )

    result = summariser.summarise(item)

    assert result.summary_text == "The filter cartridge contains..."
    assert len(result.summary_text) <= 36
