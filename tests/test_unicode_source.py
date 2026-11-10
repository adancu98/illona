from illona_mcp.bridge import IllonaBridge


def test_shipped_module_literals_do_not_depend_on_illustrator_file_encoding(tmp_path):
    bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    source = bridge._bundle("create_icon_set", {"title": "Română 🌿"}, tmp_path / "result.json")
    assert source.isascii()
    assert "Natur\\u0103" in source
    assert "Rom\\u00e2n\\u0103" in source
    assert "\\ud83c\\udf3f" in source

