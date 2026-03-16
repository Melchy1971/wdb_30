from app.domain.enums import SourceValidationStatus
from app.schemas.sources import CreateSourceRequest, UpdateSourceRequest
from app.services.source_service import SourceService


def test_validate_source_marks_supported_file_as_valid(session, workspace_tmp_path):
    file_path = workspace_tmp_path / "document.txt"
    file_path.write_text("hello", encoding="utf-8")
    service = SourceService(session)
    source = service.create_source(
        CreateSourceRequest(
            source_id="local-valid",
            display_name="Local Valid",
            location_uri=str(file_path),
        )
    )

    validated = service.validate_source(source.source_id)

    assert validated.validation_status == SourceValidationStatus.VALID.value
    assert validated.last_validated_at is not None


def test_validate_source_marks_missing_path_as_invalid(session, workspace_tmp_path):
    missing_path = workspace_tmp_path / "missing.txt"
    service = SourceService(session)
    source = service.create_source(
        CreateSourceRequest(
            source_id="local-missing",
            display_name="Local Missing",
            location_uri=str(missing_path),
        )
    )

    validated = service.validate_source(source.source_id)

    assert validated.validation_status == SourceValidationStatus.INVALID.value
    assert "does not exist" in validated.validation_message


def test_validate_source_marks_unsupported_directory_as_invalid(session, workspace_tmp_path):
    folder = workspace_tmp_path / "folder"
    folder.mkdir()
    (folder / "image.jpg").write_text("binary-ish", encoding="utf-8")
    service = SourceService(session)
    source = service.create_source(
        CreateSourceRequest(
            source_id="local-dir-invalid",
            display_name="Local Dir Invalid",
            location_uri=str(folder),
        )
    )

    validated = service.validate_source(source.source_id)

    assert validated.validation_status == SourceValidationStatus.INVALID.value
    assert "supported file types" in validated.validation_message


def test_validate_source_marks_inactive_source_as_inactive(session, workspace_tmp_path):
    file_path = workspace_tmp_path / "document.txt"
    file_path.write_text("hello", encoding="utf-8")
    service = SourceService(session)
    source = service.create_source(
        CreateSourceRequest(
            source_id="local-inactive",
            display_name="Local Inactive",
            location_uri=str(file_path),
            is_active=False,
        )
    )

    validated = service.validate_source(source.source_id)

    assert validated.validation_status == SourceValidationStatus.INACTIVE.value
    assert "inactive" in validated.validation_message


def test_validate_source_marks_unreadable_path_as_invalid(session, workspace_tmp_path, monkeypatch):
    file_path = workspace_tmp_path / "document.txt"
    file_path.write_text("hello", encoding="utf-8")
    service = SourceService(session)
    source = service.create_source(
        CreateSourceRequest(
            source_id="local-unreadable",
            display_name="Local Unreadable",
            location_uri=str(file_path),
        )
    )
    monkeypatch.setattr(SourceService, "_is_readable", staticmethod(lambda _: False))

    validated = service.validate_source(source.source_id)

    assert validated.validation_status == SourceValidationStatus.INVALID.value
    assert "not readable" in validated.validation_message


def test_update_source_resets_validation_state(session, workspace_tmp_path):
    file_path = workspace_tmp_path / "document.txt"
    file_path.write_text("hello", encoding="utf-8")
    service = SourceService(session)
    source = service.create_source(
        CreateSourceRequest(
            source_id="local-update",
            display_name="Local Update",
            location_uri=str(file_path),
        )
    )
    service.validate_source(source.source_id)

    updated = service.update_source(
        source.source_id,
        UpdateSourceRequest(location_uri=str(workspace_tmp_path / "new.txt")),
    )

    assert updated.validation_status == SourceValidationStatus.PENDING.value
    assert updated.last_validated_at is None
    assert updated.validation_message is None
