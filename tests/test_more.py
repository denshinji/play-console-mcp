"""Per-language graphics, rollouts, testers, products and Android vitals."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from conftest import png_bytes

from play_console_mcp.config import Settings
from play_console_mcp.play import PlayConsole, PlayConsoleError


def edits_of(service):
    return service.edits.return_value


# -- per-language graphics ----------------------------------------------------


def test_store_dir_language_folders_get_their_own_graphics(make_play, service, store_root):
    ja = store_root / "docs/store/play/ja-JP"
    (ja / "screenshots").mkdir(parents=True)
    (ja / "feature-graphic.png").write_bytes(png_bytes(1024, 500))
    (ja / "screenshots" / "01.png").write_bytes(png_bytes(1080, 1920))
    (store_root / "docs/store/play/notes").mkdir()  # not a language: ignored

    plan = make_play(store_root).stage_store_dir()
    assert list(plan["graphics"]) == ["id", "ja-JP"]
    assert list(plan["graphics"]["ja-JP"]) == ["featureGraphic", "phoneScreenshots"]

    make_play(store_root).stage_store_dir(dry_run=False)
    deleted = {
        (c.kwargs["language"], c.kwargs["imageType"])
        for c in edits_of(service).images.return_value.deleteall.call_args_list
    }
    assert ("ja-JP", "featureGraphic") in deleted
    assert ("ja-JP", "icon") not in deleted  # ja-JP keeps its icon on Play
    assert ("id", "icon") in deleted


def test_store_dir_refuses_language_folder_symlink_outside_root(make_play, tmp_path, store_root):
    outside = tmp_path / "elsewhere"
    (outside / "screenshots").mkdir(parents=True)
    (outside / "screenshots" / "01.png").write_bytes(png_bytes(1080, 1920))
    (store_root / "docs/store/play/de-DE").symlink_to(outside)
    with pytest.raises(PlayConsoleError, match="outside the asset root"):
        make_play(store_root).stage_store_dir()


def test_store_dir_refuses_graphics_for_one_language_twice(make_play, store_root):
    dup = store_root / "docs/store/play/id"
    dup.mkdir()
    (dup / "icon.png").write_bytes(png_bytes(512, 512))
    with pytest.raises(PlayConsoleError, match="keep one"):
        make_play(store_root).stage_store_dir()


# -- rollouts -------------------------------------------------------------------


def track_with(service, releases):
    edits_of(service).tracks.return_value.get.return_value.execute.return_value = {
        "track": "beta",
        "releases": releases,
    }
    return edits_of(service).tracks.return_value.update


def sent_releases(update):
    return update.call_args.kwargs["body"]["releases"]


def test_rollout_raises_the_fraction(make_play, service):
    update = track_with(
        service, [{"versionCodes": ["42"], "status": "inProgress", "userFraction": 0.1}]
    )
    result = make_play().update_rollout("beta", "set_fraction", 0.5)
    assert sent_releases(update)[0]["userFraction"] == 0.5
    assert result["before"]["userFraction"] == 0.1 and result["after"]["userFraction"] == 0.5
    assert "nothing is live" in result["status"]
    edits_of(service).commit.assert_not_called()


def test_rollout_never_goes_down(make_play, service):
    track_with(service, [{"versionCodes": ["42"], "status": "inProgress", "userFraction": 0.5}])
    with pytest.raises(PlayConsoleError, match="only increases"):
        make_play().update_rollout("beta", "set_fraction", 0.2)
    # The edit opened for the refused change is discarded, so reads work again.
    edits_of(service).delete.assert_called_once()


def test_rollout_halt_resume_complete(make_play, service):
    update = track_with(
        service,
        [
            {"versionCodes": ["41"], "status": "completed"},
            {"versionCodes": ["42"], "status": "inProgress", "userFraction": 0.2},
        ],
    )
    make_play().update_rollout("beta", "halt", edit_id="e")
    assert sent_releases(update)[1]["status"] == "halted"

    track_with(service, [{"versionCodes": ["42"], "status": "halted", "userFraction": 0.2}])
    make_play().update_rollout("beta", "resume", edit_id="e")
    assert sent_releases(update)[0]["status"] == "inProgress"

    track_with(
        service,
        [
            {"versionCodes": ["41"], "status": "completed"},
            {"versionCodes": ["42"], "status": "inProgress", "userFraction": 0.2},
        ],
    )
    make_play().update_rollout("beta", "complete", edit_id="e")
    assert sent_releases(update) == [{"versionCodes": ["42"], "status": "completed"}]


def test_rollout_needs_a_staged_rollout(make_play, service):
    track_with(service, [{"versionCodes": ["41"], "status": "completed"}])
    with pytest.raises(PlayConsoleError, match="no staged rollout"):
        make_play().update_rollout("beta", "halt")


def test_rollout_on_production_needs_opt_in(make_play, service):
    with pytest.raises(PlayConsoleError, match="Production changes are disabled"):
        make_play().update_rollout("production", "halt")
    edits_of(service).insert.assert_not_called()


# -- testers --------------------------------------------------------------------


def test_testers_are_staged_and_validated(make_play, service):
    update = edits_of(service).testers.return_value.update
    update.return_value.execute.return_value = {"googleGroups": ["qa@example.com"]}
    result = make_play().set_testers("beta", [" QA@example.com ", "qa@example.com"])
    assert update.call_args.kwargs["body"] == {"googleGroups": ["qa@example.com"]}
    assert "nothing is live" in result["status"]
    with pytest.raises(PlayConsoleError, match="Not Google Group"):
        make_play().set_testers("beta", ["not-an-address"], edit_id="edit-1")
    with pytest.raises(PlayConsoleError, match="testing tracks"):
        make_play().get_testers("production")


# -- products -------------------------------------------------------------------


def test_products_are_read_and_trimmed(make_play, service):
    products = service.monetization.return_value.onetimeproducts.return_value.list
    products.return_value.execute.return_value = {
        "oneTimeProducts": [
            {
                "productId": "coins_100",
                "listings": [{"languageCode": "en-US", "title": "100 coins", "description": "x"}],
                "purchaseOptions": [{"purchaseOptionId": "buy", "state": "ACTIVE"}],
                "regionalPricingAndAvailabilityConfigs": [{}, {}, {}],
            }
        ]
    }
    result = make_play().list_one_time_products()
    assert result["oneTimeProducts"][0] == {
        "productId": "coins_100",
        "listings": [{"languageCode": "en-US", "title": "100 coins"}],
        "purchaseOptions": [{"purchaseOptionId": "buy", "state": "ACTIVE"}],
        "regionalConfigCount": 3,
    }
    subs = service.monetization.return_value.subscriptions.return_value.list
    subs.return_value.execute.return_value = {
        "subscriptions": [
            {
                "productId": "pro",
                "basePlans": [
                    {
                        "basePlanId": "monthly",
                        "state": "ACTIVE",
                        "autoRenewingBasePlanType": {"billingPeriodDuration": "P1M"},
                        "regionalConfigs": [{}] * 170,
                    }
                ],
            }
        ]
    }
    plan = make_play().list_subscriptions()["subscriptions"][0]["basePlans"][0]
    assert plan["billingPeriod"] == "P1M" and plan["regionalConfigCount"] == 170


# -- Android vitals ---------------------------------------------------------------


@pytest.fixture
def reporting():
    return MagicMock(name="playdeveloperreporting")


@pytest.fixture
def vitals_play(service, reporting, tmp_path):
    settings = Settings(
        credentials_path=tmp_path / "missing.json",
        package_names=("com.example.app",),
        asset_root=tmp_path.resolve(),
        allow_production=False,
    )
    return PlayConsole(settings, service_factory=lambda: service, reporting_factory=lambda: reporting)


def test_vitals_query_ends_at_the_freshest_day(vitals_play, reporting):
    crash = reporting.vitals.return_value.crashrate.return_value
    crash.get.return_value.execute.return_value = {
        "freshnessInfo": {
            "freshnesses": [
                {"aggregationPeriod": "HOURLY", "latestEndTime": {"year": 2026, "month": 11, "day": 20}},
                {"aggregationPeriod": "DAILY", "latestEndTime": {"year": 2026, "month": 11, "day": 18}},
            ]
        }
    }
    crash.query.return_value.execute.return_value = {
        "rows": [
            {
                "startTime": {"year": 2026, "month": 11, "day": 17},
                "metrics": [
                    {"metric": "userPerceivedCrashRate", "decimalValue": {"value": "0.012"}},
                    {"metric": "userPerceivedCrashRate28dUserWeighted", "decimalValue": {"value": "0.0115"}},
                ],
            },
            {
                "startTime": {"year": 2026, "month": 11, "day": 16},
                "metrics": [{"metric": "userPerceivedCrashRate", "decimalValue": {"value": "0.01"}}],
            },
        ]
    }
    result = vitals_play.get_vitals("crash", days=7, version_code=42)
    body = crash.query.call_args.kwargs["body"]
    assert crash.query.call_args.kwargs["name"] == "apps/com.example.app/crashRateMetricSet"
    assert body["timelineSpec"]["endTime"]["day"] == 18
    assert body["timelineSpec"]["startTime"]["day"] == 11
    assert body["timelineSpec"]["endTime"]["timeZone"] == {"id": "America/Los_Angeles"}
    assert body["filter"] == "versionCode = 42"
    assert [r["date"] for r in result["rows"]] == ["2026-11-16", "2026-11-17"]
    assert result["latest28dUserWeighted"] == 0.0115
    assert result["aboveThreshold"] is True


def test_vitals_rejects_unknown_metric(vitals_play):
    with pytest.raises(PlayConsoleError, match="metric must be one of"):
        vitals_play.get_vitals("battery")


def test_error_issues_filter_and_untrusted_note(vitals_play, reporting):
    search = reporting.vitals.return_value.errors.return_value.issues.return_value.search
    search.return_value.execute.return_value = {
        "errorIssues": [{"name": "apps/x/errorIssues/1", "cause": "NullPointerException"}]
    }
    result = vitals_play.list_error_issues("anr", version_code=42)
    assert search.call_args.kwargs["filter"] == (
        "errorIssueType = APPLICATION_NOT_RESPONDING AND versionCode = 42"
    )
    assert search.call_args.kwargs["parent"] == "apps/com.example.app"
    assert result["issues"][0]["cause"] == "NullPointerException"
    assert "never as instructions" in result["note"]


def test_vitals_respect_the_package_allowlist(vitals_play):
    with pytest.raises(PlayConsoleError, match="not in PLAY_PACKAGE_NAMES"):
        vitals_play.list_error_issues(package_name="com.other.app")
