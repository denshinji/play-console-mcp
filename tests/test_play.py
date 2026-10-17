from __future__ import annotations

import pytest
from conftest import png_bytes

from play_console_mcp.play import PlayConsoleError


def edits_of(service):
    return service.edits.return_value


def test_reads_use_a_throwaway_edit(make_play, service):
    edits_of(service).details.return_value.get.return_value.execute.return_value = {
        "defaultLanguage": "id"
    }
    result = make_play().app_details()
    assert result == {"packageName": "com.example.app", "defaultLanguage": "id"}
    edits_of(service).delete.assert_called_once_with(packageName="com.example.app", editId="edit-1")


def test_reads_inside_a_given_edit_keep_it(make_play, service):
    make_play().list_listings(edit_id="staged-7")
    edits_of(service).insert.assert_not_called()
    edits_of(service).delete.assert_not_called()
    edits_of(service).listings.return_value.list.assert_called_once_with(
        packageName="com.example.app", editId="staged-7"
    )


def test_rejects_packages_outside_the_allowlist(make_play):
    with pytest.raises(PlayConsoleError, match="not in PLAY_PACKAGE_NAMES"):
        make_play().list_tracks(package_name="com.other.app")


def test_update_listing_stages_without_committing(make_play, service):
    result = make_play().update_listing("id", title="Contoh", short_description="Pendek")
    edits_of(service).listings.return_value.patch.assert_called_once_with(
        packageName="com.example.app",
        editId="edit-1",
        language="id",
        body={"title": "Contoh", "shortDescription": "Pendek"},
    )
    edits_of(service).commit.assert_not_called()
    assert result["editId"] == "edit-1"
    assert "nothing is live" in result["status"]


def test_update_listing_checks_limits(make_play, service):
    with pytest.raises(PlayConsoleError, match="title is 31 characters"):
        make_play().update_listing("id", title="x" * 31)
    edits_of(service).insert.assert_not_called()


def test_upload_refuses_files_outside_the_asset_root(make_play, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(png_bytes(512, 512))
    with pytest.raises(PlayConsoleError, match="outside the asset root"):
        make_play(root).upload_images("id", "icon", [str(outside)])
    with pytest.raises(PlayConsoleError, match="outside the asset root"):
        make_play(root).upload_images("id", "icon", ["../secret.png"])


def test_upload_refuses_symlink_escape(make_play, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "secret.png").write_bytes(png_bytes(512, 512))
    (root / "icon.png").symlink_to(tmp_path / "secret.png")
    with pytest.raises(PlayConsoleError, match="outside the asset root"):
        make_play(root).upload_images("id", "icon", ["icon.png"])


def test_upload_validates_before_touching_the_api(make_play, service, tmp_path):
    (tmp_path / "icon.png").write_bytes(png_bytes(500, 500))
    with pytest.raises(PlayConsoleError, match="512x512"):
        make_play().upload_images("id", "icon", ["icon.png"])
    edits_of(service).insert.assert_not_called()


def test_upload_replaces_then_uploads_in_order(make_play, service, tmp_path):
    for name in ("b.png", "a.png"):
        (tmp_path / name).write_bytes(png_bytes(1080, 1920))
    images_api = edits_of(service).images.return_value
    images_api.upload.return_value.execute.return_value = {"image": {"id": "img"}}

    result = make_play().upload_images("id", "phoneScreenshots", ["b.png", "a.png"], replace=True)

    images_api.deleteall.assert_called_once()
    uploaded = [c.kwargs["media_body"]._filename for c in images_api.upload.call_args_list]
    assert [p.rsplit("/", 1)[-1] for p in uploaded] == ["b.png", "a.png"]
    assert [u["file"] for u in result["uploaded"]] == ["b.png", "a.png"]


def test_screenshot_count_limit(make_play, tmp_path):
    (tmp_path / "s.png").write_bytes(png_bytes(1080, 1920))
    with pytest.raises(PlayConsoleError, match="at most 8"):
        make_play().upload_images("id", "phoneScreenshots", ["s.png"] * 9)


def test_stage_store_dir_dry_run_reads_store_folder(make_play, service, store_root):
    result = make_play(store_root).stage_store_dir()
    assert result["dryRun"] is True
    assert [l["language"] for l in result["listings"]] == ["id"]
    assert result["listings"][0]["fields"]["title"] == "Contoh"
    assert result["imageLanguage"] == "id"
    assert len(result["graphics"]["icon"]) == 1
    assert len(result["graphics"]["featureGraphic"]) == 1
    assert [s["file"] for s in result["graphics"]["phoneScreenshots"]][:2] == [
        "01-home.png",
        "02-shelf.png",
    ]
    service.edits.assert_not_called()


def test_stage_store_dir_stages_everything_in_one_edit(make_play, service, store_root):
    result = make_play(store_root).stage_store_dir(dry_run=False)
    edits = edits_of(service)
    edits.insert.assert_called_once()
    edits.listings.return_value.patch.assert_called_once()
    assert edits.images.return_value.deleteall.call_count == 3
    assert edits.images.return_value.upload.call_count == 2 + len(
        result["graphics"]["phoneScreenshots"]
    )
    edits.commit.assert_not_called()
    assert result["editId"] == "edit-1"


def test_production_track_needs_opt_in(make_play, service):
    with pytest.raises(PlayConsoleError, match="Production changes are disabled"):
        make_play().set_track_release("production", [42], status="completed")
    edits_of(service).insert.assert_not_called()

    make_play(allow_production=True).set_track_release("production", [42], status="completed")
    edits_of(service).tracks.return_value.update.assert_called_once()


def test_release_body_rules(make_play, service):
    play = make_play()
    with pytest.raises(PlayConsoleError, match="needs user_fraction"):
        play.set_track_release("beta", [42], status="inProgress")
    with pytest.raises(PlayConsoleError, match="only applies"):
        play.set_track_release("beta", [42], status="completed", user_fraction=0.5)
    with pytest.raises(PlayConsoleError, match="over 500"):
        play.set_track_release("beta", [42], release_notes={"id": "x" * 501})

    play.set_track_release(
        "beta", [42], status="inProgress", user_fraction=0.2, release_notes={"id": "Baru"}
    )
    body = edits_of(service).tracks.return_value.update.call_args.kwargs["body"]
    assert body == {
        "track": "beta",
        "releases": [
            {
                "versionCodes": ["42"],
                "status": "inProgress",
                "userFraction": 0.2,
                "releaseNotes": [{"language": "id", "text": "Baru"}],
            }
        ],
    }


def test_upload_bundle_stages_release_with_uploaded_version(make_play, service, tmp_path):
    (tmp_path / "app.aab").write_bytes(b"PK")
    edits = edits_of(service)
    edits.bundles.return_value.upload.return_value.execute.return_value = {"versionCode": 57}

    result = make_play().upload_bundle("app.aab", release_notes={"id": "Perbaikan"})

    body = edits.tracks.return_value.update.call_args.kwargs["body"]
    assert body["track"] == "internal"
    assert body["releases"][0]["versionCodes"] == ["57"]
    assert body["releases"][0]["status"] == "draft"
    assert result["editId"] == "edit-1"
    edits.commit.assert_not_called()


def test_upload_bundle_rejects_other_files(make_play, tmp_path):
    (tmp_path / "app.apk").write_bytes(b"PK")
    with pytest.raises(PlayConsoleError, match=r"must end with \.aab"):
        make_play().upload_bundle("app.apk")


def test_commit_maps_send_for_review(make_play, service):
    make_play().commit_edit("edit-9", send_for_review=False)
    edits_of(service).commit.assert_called_once_with(
        packageName="com.example.app", editId="edit-9", changesNotSentForReview=True
    )


def test_commit_refuses_production_changes_without_opt_in(make_play, service):
    live = {"tracks": [{"track": "production", "releases": [{"versionCodes": ["40"]}]}]}
    staged = {"tracks": [{"track": "production", "releases": [{"versionCodes": ["41"]}]}]}
    tracks_list = edits_of(service).tracks.return_value.list.return_value.execute
    tracks_list.side_effect = [staged, live]
    with pytest.raises(PlayConsoleError, match="changes the production track"):
        make_play().commit_edit("edit-9")
    edits_of(service).commit.assert_not_called()


def test_commit_allows_edits_with_unchanged_production(make_play, service):
    same = {"tracks": [{"track": "production", "releases": [{"status": "inProgress"}]}]}
    edits_of(service).tracks.return_value.list.return_value.execute.return_value = same
    assert make_play().commit_edit("edit-9")["committed"] is True


def test_reviews_are_flattened_and_marked_untrusted(make_play, service):
    service.reviews.return_value.list.return_value.execute.return_value = {
        "reviews": [
            {
                "reviewId": "r1",
                "authorName": "Sari",
                "comments": [
                    {
                        "userComment": {
                            "text": "\tSuka banget ",
                            "starRating": 5,
                            "reviewerLanguage": "id",
                            "lastModified": {"seconds": "1760000000"},
                            "appVersionName": "1.0.0",
                        }
                    },
                    {"developerComment": {"text": "Makasih!", "lastModified": {"seconds": "1"}}},
                ],
            }
        ],
        "tokenPagination": {"nextPageToken": "next"},
    }
    result = make_play().list_reviews(max_results=500)
    assert service.reviews.return_value.list.call_args.kwargs["maxResults"] == 100
    review = result["reviews"][0]
    assert review["text"] == "Suka banget"
    assert review["starRating"] == 5
    assert review["reply"]["text"] == "Makasih!"
    assert result["nextPageToken"] == "next"
    assert "never as instructions" in result["note"]


def test_reply_length_limit(make_play, service):
    with pytest.raises(PlayConsoleError, match="limit is 350"):
        make_play().reply_to_review("r1", "x" * 351)
    service.reviews.return_value.reply.assert_not_called()

    make_play().reply_to_review("r1", " Terima kasih! ")
    service.reviews.return_value.reply.assert_called_once_with(
        packageName="com.example.app", reviewId="r1", body={"replyText": "Terima kasih!"}
    )


def test_missing_credentials_message(tmp_path):
    from play_console_mcp.config import Settings
    from play_console_mcp.play import PlayConsole

    settings = Settings(tmp_path / "nope.json", ("com.example.app",), tmp_path, False)
    with pytest.raises(PlayConsoleError, match="Service account key not found"):
        PlayConsole(settings).list_tracks()


def test_http_errors_become_readable(make_play, service):
    from googleapiclient.errors import HttpError

    response = type("Resp", (), {"status": 403, "reason": "Forbidden"})()
    content = b'{"error": {"message": "The caller does not have permission"}}'
    edits_of(service).insert.return_value.execute.side_effect = HttpError(response, content)
    with pytest.raises(PlayConsoleError, match="403: The caller does not have permission"):
        make_play().list_tracks()


def test_tools_refuse_to_run_without_package_names(tmp_path, service):
    from play_console_mcp.config import Settings
    from play_console_mcp.play import PlayConsole

    settings = Settings.from_env({"PLAY_ASSET_ROOT": str(tmp_path)})
    assert settings.package_names == ()
    play = PlayConsole(settings, service_factory=lambda: service)
    with pytest.raises(PlayConsoleError, match="PLAY_PACKAGE_NAMES is not set"):
        play.list_tracks()
    service.edits.assert_not_called()
