"""
===============================================================================
BLOCK COMMENT: EKP V3 CLEANER FRAMEWORK & PIPELINE TESTS
Module: backend/tests/test_ekp_cleaner.py
Author: EKP Architecture Team
Description:
    Pytest suite verifying the dynamic 1..N step CleanerPipeline, CleanerStepRegistry,
    custom step subclassing, enable/disable toggles, configuration overrides,
    and text cleaning transformations.
===============================================================================
"""

import pytest
from app.knowledge.ekp_v3.cleaner_base import (
    CleanerStep, CleanerStepRegistry, CleanerPipeline
)
from app.knowledge.ekp_v3.cleaner import (
    HyphenationRepairStep,
    WhitespaceNormalizationStep,
    HeaderFooterFilterStep,
    OCRDeduplicationStep,
    MarkdownTableFormatStep,
    ImageContextFormatStep,
    SmartParagraphAssemblyStep,
    get_default_pipeline,
    clean_and_deduplicate_text,
    smart_paragraph_assembly
)


def test_hyphenation_repair_step():
    step = HyphenationRepairStep()
    text = "The docu-\nmentation was trans-\nformed successfully."
    cleaned = step.process(text)
    assert cleaned == "The documentation was transformed successfully."


def test_whitespace_normalization_step():
    step = WhitespaceNormalizationStep(config={"max_consecutive_newlines": 2})
    text = "Line 1  with   extra   spaces .\n\n\n\nLine 2 after multi-newlines ."
    cleaned = step.process(text)
    assert cleaned == "Line 1 with extra spaces.\n\nLine 2 after multi-newlines."


def test_header_footer_filter_step():
    step = HeaderFooterFilterStep()
    text = "Page 1 of 10\nActual content line.\n- 1 -\nAnother content line."
    cleaned = step.process(text)
    assert cleaned == "Actual content line.\nAnother content line."


def test_ocr_deduplication_step():
    step = OCRDeduplicationStep()
    text = "THE HIGH COURT OF JUDICATURE AT BOMBAY THE HIGH COURT OF JUDICATURE AT BOMBAY\nCORAM CORAM: JUSTICE SMITH"
    cleaned = step.process(text)
    assert cleaned == "THE HIGH COURT OF JUDICATURE AT BOMBAY\nCORAM: JUSTICE SMITH"


def test_markdown_table_format_step():
    step = MarkdownTableFormatStep()
    text = "|   Col A   |   Col B   |\n| val1 | val2 |"
    cleaned = step.process(text)
    assert cleaned == "| Col A | Col B |\n| val1 | val2 |"


def test_image_context_format_step():
    step = ImageContextFormatStep()
    text = "[IMAGE: architecture_diagram.png]"
    cleaned = step.process(text)
    assert cleaned == "![Image context: architecture_diagram.png](architecture_diagram.png)"


def test_smart_paragraph_assembly_step():
    step = SmartParagraphAssemblyStep()
    text = "This is a sentence that is split\nacross multiple lines without\nterminal punctuation.\n\n# Header 1\n* Bullet 1"
    cleaned = step.process(text)
    assert "This is a sentence that is split across multiple lines without terminal punctuation." in cleaned
    assert "# Header 1" in cleaned
    assert "* Bullet 1" in cleaned


def test_cleaner_pipeline_dynamic_toggles():
    pipeline = CleanerPipeline()
    s1 = HyphenationRepairStep(name="step_hyphen", enabled=True)
    s2 = WhitespaceNormalizationStep(name="step_space", enabled=True)
    pipeline.add_step(s1).add_step(s2)

    assert len(pipeline.steps) == 2

    # Disable step 1
    pipeline.disable_step("step_hyphen")
    assert not s1.enabled

    # Enable step 1
    pipeline.enable_step("step_hyphen")
    assert s1.enabled

    # Remove step
    pipeline.remove_step("step_space")
    assert len(pipeline.steps) == 1


def test_cleaner_step_registry():
    assert "hyphenation_repair" in CleanerStepRegistry.list_registered()
    assert "whitespace_normalization" in CleanerStepRegistry.list_registered()

    config = [
        {"step": "hyphenation_repair", "enabled": True},
        {"step": "whitespace_normalization", "enabled": False, "config": {"max_consecutive_newlines": 1}}
    ]

    pipeline = CleanerPipeline.from_config(config)
    assert len(pipeline.steps) == 2
    assert pipeline.steps[0].enabled is True
    assert pipeline.steps[1].enabled is False


def test_custom_pluggable_step():
    @CleanerStepRegistry.register("custom_legal_cleaner")
    class CustomLegalCleanerStep(CleanerStep):
        def process(self, text: str, context=None) -> str:
            return text.replace("PLAINTIFF", "Plaintiff (Party)")

    config = [{"step": "custom_legal_cleaner", "enabled": True}]
    pipeline = CleanerPipeline.from_config(config)
    res = pipeline.run("PLAINTIFF vs DEFENDANT")
    assert res == "Plaintiff (Party) vs DEFENDANT"


def test_legacy_helper_wrappers():
    raw = "The docu-\nmentation was   good.\nPage 1 of 5"
    cleaned = clean_and_deduplicate_text(raw)
    assert "documentation was good." in cleaned
    assert "Page 1 of 5" not in cleaned

    paragraphs = smart_paragraph_assembly("First line\nsecond line.\n\nSecond paragraph.")
    assert len(paragraphs) == 2
    assert paragraphs[0] == "First line second line."
