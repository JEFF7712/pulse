def test_write_daily_digest_creates_parent_directory_and_file(tmp_path):
    from pulse.vault.writer import write_daily_digest

    content = "# 2026-03-22\n\n## Timeline\n- Morning run"

    output_path = write_daily_digest(
        vault_root=tmp_path,
        date_slug="2026-03-22",
        content=content,
    )

    assert output_path == tmp_path / "01-Daily" / "2026-03-22.md"
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == content
