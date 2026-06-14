import ast
import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from document_digitization_ai.media import (
    MediaStagingConfigurationError,
    MediaStagingError,
    MediaStagingInput,
    StagedMediaReferenceKind,
)
from document_digitization_ai.media.imgbb import (
    HTTPResponseData,
    IMGBB_MAX_EXPIRATION_SECONDS,
    IMGBB_MIN_EXPIRATION_SECONDS,
    ImgBBMediaStagingService,
)


FORBIDDEN_NETWORK_MODULES = (
    "urllib",
    "socket",
    "http.client",
)

MEDIA_MODULES_WITHOUT_TRANSPORT = (
    Path("src/document_digitization_ai/media/base.py"),
    Path("src/document_digitization_ai/media/local.py"),
)


@pytest.mark.asyncio
async def test_imgbb_upload_uses_fake_transport_and_public_url_reference(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    transport = FakeImgBBHTTPTransport(
        response=_successful_response(
            direct_url="https://i.ibb.co/example/staged.jpg",
            delete_url="https://ibb.co/delete/private-token",
        )
    )
    service = ImgBBMediaStagingService(
        api_key="fake-imgbb-key",
        ttl_seconds=3600,
        transport=transport,
    )

    result = await service.stage(
        MediaStagingInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            sha256="d" * 64,
            metadata={"job_id": "job-001"},
        )
    )

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.url == "https://api.imgbb.com/1/upload"
    assert call.timeout_seconds == 180
    assert call.fields["key"] == "fake-imgbb-key"
    assert call.fields["expiration"] == "3600"
    assert call.fields["image"] == base64.b64encode(b"fake-image-bytes").decode(
        "ascii"
    )
    assert result.external_upload_performed is True
    assert result.reference.kind is StagedMediaReferenceKind.PUBLIC_URL
    assert result.reference.value == "https://i.ibb.co/example/staged.jpg"
    assert result.reference.mime_type == "image/jpeg"
    assert result.reference.file_size_bytes == image_path.stat().st_size
    assert result.reference.sha256 == "d" * 64
    assert result.reference.metadata["staging_backend"] == "imgbb"
    assert result.reference.metadata["private_cleanup_url_available"] is True


@pytest.mark.asyncio
async def test_imgbb_provider_facing_reference_does_not_leak_local_path_or_delete_url(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "nested" / "original.jpg")
    transport = FakeImgBBHTTPTransport(
        response=_successful_response(
            direct_url="https://i.ibb.co/example/public.jpg",
            delete_url="https://ibb.co/delete/private-token",
        )
    )
    service = ImgBBMediaStagingService(
        api_key="fake-imgbb-key",
        transport=transport,
    )

    result = await service.stage(
        MediaStagingInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
        )
    )
    provider_payload = result.reference.to_dict()
    serialized_payload = json.dumps(provider_payload, sort_keys=True)

    assert str(image_path) not in serialized_payload
    assert "private-token" not in serialized_payload
    assert "delete_url" not in serialized_payload
    assert provider_payload["value"] == "https://i.ibb.co/example/public.jpg"


@pytest.mark.asyncio
async def test_imgbb_response_url_fallbacks_are_supported(tmp_path: Path) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    response = HTTPResponseData(
        status_code=200,
        body=json.dumps(
            {
                "success": True,
                "data": {
                    "id": "img-001",
                    "display_url": "https://i.ibb.co/example/display.jpg",
                },
            }
        ).encode("utf-8"),
    )
    service = ImgBBMediaStagingService(
        api_key="fake-imgbb-key",
        transport=FakeImgBBHTTPTransport(response=response),
    )

    result = await service.stage(
        MediaStagingInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
        )
    )

    assert result.reference.value == "https://i.ibb.co/example/display.jpg"
    assert result.reference.metadata["provider_facing_url_source"] == "data.display_url"
    assert result.reference.metadata["imgbb_id"] == "img-001"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error_match"),
    [
        (HTTPResponseData(status_code=500, body=b"{}"), "HTTP status 500"),
        (HTTPResponseData(status_code=200, body=b"not-json"), "not valid JSON"),
        (
            HTTPResponseData(
                status_code=200,
                body=json.dumps({"success": False, "data": {}}).encode("utf-8"),
            ),
            "success=false",
        ),
        (
            HTTPResponseData(
                status_code=200,
                body=json.dumps({"success": True, "data": {}}).encode("utf-8"),
            ),
            "missing public image URL",
        ),
        (
            HTTPResponseData(
                status_code=200,
                body=json.dumps(
                    {
                        "success": True,
                        "data": {"image": {"url": "C:/tmp/local.jpg"}},
                    }
                ).encode("utf-8"),
            ),
            "must be HTTP",
        ),
    ],
)
async def test_imgbb_bad_responses_raise_media_staging_error(
    tmp_path: Path,
    response: HTTPResponseData,
    error_match: str,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    service = ImgBBMediaStagingService(
        api_key="fake-imgbb-key",
        transport=FakeImgBBHTTPTransport(response=response),
    )

    with pytest.raises(MediaStagingError, match=error_match):
        await service.stage(
            MediaStagingInput(
                local_path=image_path,
                mime_type="image/jpeg",
                file_size_bytes=image_path.stat().st_size,
            )
        )


@pytest.mark.parametrize(
    "ttl_seconds",
    [
        IMGBB_MIN_EXPIRATION_SECONDS - 1,
        IMGBB_MAX_EXPIRATION_SECONDS + 1,
    ],
)
def test_imgbb_rejects_ttl_outside_supported_range(ttl_seconds: int) -> None:
    with pytest.raises(MediaStagingConfigurationError, match="MEDIA_STAGING_TTL_SECONDS"):
        ImgBBMediaStagingService(
            api_key="fake-imgbb-key",
            ttl_seconds=ttl_seconds,
            transport=FakeImgBBHTTPTransport(response=_successful_response()),
        )


def test_imgbb_service_repr_does_not_include_api_key() -> None:
    service = ImgBBMediaStagingService(
        api_key="fake-imgbb-key",
        transport=FakeImgBBHTTPTransport(response=_successful_response()),
    )

    assert "fake-imgbb-key" not in repr(service)


def test_network_imports_stay_outside_non_transport_media_modules() -> None:
    for module_path in MEDIA_MODULES_WITHOUT_TRANSPORT:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(imported_module, FORBIDDEN_NETWORK_MODULES)


@dataclass(frozen=True, slots=True)
class TransportCall:
    url: str
    fields: Mapping[str, str]
    timeout_seconds: int


@dataclass(slots=True)
class FakeImgBBHTTPTransport:
    response: HTTPResponseData
    calls: list[TransportCall] = field(default_factory=list)

    def post_form(
        self,
        url: str,
        fields: Mapping[str, str],
        *,
        timeout_seconds: int,
    ) -> HTTPResponseData:
        self.calls.append(
            TransportCall(
                url=url,
                fields=dict(fields),
                timeout_seconds=timeout_seconds,
            )
        )
        return self.response


def _successful_response(
    *,
    direct_url: str = "https://i.ibb.co/example/staged.jpg",
    delete_url: str | None = None,
) -> HTTPResponseData:
    data: dict[str, object] = {
        "id": "img-001",
        "image": {"url": direct_url},
    }
    if delete_url is not None:
        data["delete_url"] = delete_url
    return HTTPResponseData(
        status_code=200,
        body=json.dumps({"success": True, "data": data}).encode("utf-8"),
    )


def _write_image_bytes(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-image-bytes")
    return path


def _imported_module_names(module_path: Path) -> tuple[str, ...]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
    return tuple(imported_modules)


def _matches_any_import(imported_module: str, blocked_modules: tuple[str, ...]) -> bool:
    return any(
        imported_module == blocked_module
        or imported_module.startswith(f"{blocked_module}.")
        for blocked_module in blocked_modules
    )
