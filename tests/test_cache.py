from screening import cache


def test_round_trip(tmp_path):
    cache.write(str(tmp_path), "k", {"a": 1})
    assert cache.read(str(tmp_path), "k", ttl_seconds=999) == {"a": 1}


def test_read_returns_none_for_corrupt_file(tmp_path):
    cache.write(str(tmp_path), "k", {"a": 1})
    # clobber the stored file with junk
    stored = next(tmp_path.glob("*.json"))
    stored.write_text("not json", "utf-8")
    assert cache.read(str(tmp_path), "k", ttl_seconds=999) is None


def test_write_failure_is_swallowed(tmp_path, caplog):
    # a non-serialisable value would raise inside json.dumps
    cache.write(str(tmp_path), "k", {1, 2, 3})
    assert cache.read(str(tmp_path), "k", ttl_seconds=999) is None
    assert "could not write cache entry" in caplog.text


def test_read_honours_ttl(tmp_path):
    cache.write(str(tmp_path), "k", {"a": 1})
    assert cache.read(str(tmp_path), "k", ttl_seconds=-1) is None
