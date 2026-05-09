"""Tests for the marble package."""

from src.marble.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


def test_expected_nodes_registered():
    assert set(NODE_CLASS_MAPPINGS.keys()) == {
        "MarbleGenerateWorld",
        "MarbleFetchImage",
        "MarbleFetchMesh",
        "MarbleSaveSPZ",
    }


def test_display_names_match_class_keys():
    assert set(NODE_DISPLAY_NAME_MAPPINGS.keys()) == set(NODE_CLASS_MAPPINGS.keys())


def test_each_node_declares_required_attributes():
    for name, cls in NODE_CLASS_MAPPINGS.items():
        assert hasattr(cls, "INPUT_TYPES"), f"{name} missing INPUT_TYPES"
        assert hasattr(cls, "RETURN_TYPES"), f"{name} missing RETURN_TYPES"
        assert hasattr(cls, "FUNCTION"), f"{name} missing FUNCTION"
        assert hasattr(cls, "CATEGORY"), f"{name} missing CATEGORY"
        assert cls.CATEGORY == "Marble"
        assert hasattr(cls, cls.FUNCTION), f"{name} missing method {cls.FUNCTION}"


def test_every_input_has_a_tooltip():
    """Lock-in: every node input must declare a tooltip so the UI is self-documenting."""
    for node_name, cls in NODE_CLASS_MAPPINGS.items():
        schema = cls.INPUT_TYPES()
        for category in ("required", "optional"):
            for field_name, spec in schema.get(category, {}).items():
                assert isinstance(spec, tuple) and len(spec) >= 2 and isinstance(spec[1], dict), (
                    f"{node_name}.{field_name} has no config dict — add one with a 'tooltip' key"
                )
                assert spec[1].get("tooltip"), f"{node_name}.{field_name} is missing a tooltip"
