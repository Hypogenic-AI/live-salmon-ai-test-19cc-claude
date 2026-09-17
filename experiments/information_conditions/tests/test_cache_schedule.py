from infocond import cache, schedule


def _key(**kw):
    base = dict(phase="smoke", dataset="live_salmon", condition="A", model_id="openai/gpt-4.1",
                prompt_hash="abc", request_settings={"temperature": 0.7, "max_tokens": 4096, "seed": None}, rep=1)
    base.update(kw)
    return cache.cache_key(**base)


def test_cache_key_separates_every_identity_component():
    k = _key()
    assert k == _key()
    assert k != _key(phase="formal")
    assert k != _key(dataset="dead_salmon")
    assert k != _key(condition="A_prime")
    assert k != _key(model_id="anthropic/claude-sonnet-4.5")
    assert k != _key(prompt_hash="abd")
    assert k != _key(request_settings={"temperature": 0.0, "max_tokens": 4096, "seed": None})
    assert k != _key(request_settings={"temperature": 0.7, "max_tokens": 4096, "seed": 1})
    assert k != _key(rep=2)
    assert cache.record_filename("smoke", "live_salmon", "A", "gpt-4.1", 1, k).startswith("smoke__live_salmon__A__gpt-4.1__rep01__")


def test_schedule_counts_and_determinism(cfg, bundles):
    s1 = schedule.build_schedule("smoke", cfg, bundles, "gpt-4.1", "openai/gpt-4.1")
    s2 = schedule.build_schedule("smoke", cfg, bundles, "gpt-4.1", "openai/gpt-4.1")
    assert s1 == s2
    assert s1["planned_calls"] == 6 and s1["repetitions_per_combination"] == 1
    f = schedule.build_schedule("formal", cfg, bundles, "gpt-4.1", "openai/gpt-4.1")
    assert f["planned_calls"] == 30 and f["repetitions_per_combination"] == 5
    combos = {(c["dataset"], c["condition"]) for c in f["calls"]}
    assert len(combos) == 6
    reps = sorted(c["rep"] for c in f["calls"] if c["dataset"] == "live_salmon" and c["condition"] == "B")
    assert reps == [1, 2, 3, 4, 5]
    assert s1["scheduling_seed"] == cfg["scheduling_seed"] and s1["seed_string"].endswith(":smoke")
    # shuffled order differs from canonical order, and schedule_index is a permutation
    assert [c["schedule_index"] for c in f["calls"]] == list(range(30))
    canonical = [(d, c, r) for d in ("live_salmon", "dead_salmon") for c in cfg["conditions"] for r in range(1, 6)]
    assert [(c["dataset"], c["condition"], c["rep"]) for c in f["calls"]] != canonical


def test_smoke_and_formal_keys_never_collide(cfg, bundles):
    s = schedule.build_schedule("smoke", cfg, bundles, "gpt-4.1", "openai/gpt-4.1")
    f = schedule.build_schedule("formal", cfg, bundles, "gpt-4.1", "openai/gpt-4.1")
    assert not ({c["cache_key"] for c in s["calls"]} & {c["cache_key"] for c in f["calls"]})
    assert all(c["record_file"].startswith("smoke__") for c in s["calls"])
    assert all(c["record_file"].startswith("formal__") for c in f["calls"])
