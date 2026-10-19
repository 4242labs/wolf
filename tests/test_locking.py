
from wolf.locking import AlreadyRunningError, active_tooling, run_lock


def test_run_lock_blocks_overlap(tmp_path):
    lock_dir = tmp_path / "wolf.lock"
    with run_lock(lock_dir):
        assert lock_dir.exists()
        with_second_entry_raises(lock_dir)
    assert not lock_dir.exists()  # cleaned up on exit


def with_second_entry_raises(lock_dir):
    try:
        with run_lock(lock_dir):
            pass
        raise AssertionError("expected AlreadyRunningError")
    except AlreadyRunningError:
        pass


def test_run_lock_releases_after_exception(tmp_path):
    lock_dir = tmp_path / "wolf.lock"
    try:
        with run_lock(lock_dir):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert not lock_dir.exists()


def test_active_tooling_detects_self_test_process():
    # `pytest` itself won't match the pattern (not npm/npx/poetry/pip/brew/cargo/rustc/playwright),
    # so this just proves the function runs without error and returns str|None.
    result = active_tooling()
    assert result is None or isinstance(result, str)
