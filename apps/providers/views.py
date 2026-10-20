"""Provider 设置 API。"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.exceptions import ApiError

from .models import ProviderProfile
from .services import (
    KINDS,
    seed_from_env,
    test_provider,
    validate_base_url,
)


def _payload_for(profile: ProviderProfile, reveal: bool) -> dict:
    return profile.as_dict(reveal=reveal)


def _set_default(profile: ProviderProfile) -> None:
    with transaction.atomic():
        ProviderProfile.objects.filter(kind=profile.kind).exclude(pk=profile.pk).update(is_default=False)
        profile.is_default = True
        profile.save(update_fields=["is_default", "updated_at"])


@api_view(["GET", "POST"])
def providers_view(request):
    if request.method == "GET":
        seed_from_env()
        reveal = str(request.query_params.get("reveal", "")).lower() in {"1", "true", "yes"}
        kind = request.query_params.get("kind")
        queryset = ProviderProfile.objects.all()
        if kind:
            if kind not in KINDS:
                raise ApiError("INVALID_PROVIDER_KIND", f"未知 Provider 类型：{kind}", 400)
            queryset = queryset.filter(kind=kind)
        items = [_payload_for(item, reveal) for item in queryset]
        return Response({"ok": True, "items": items, "kinds": list(KINDS)})

    data = request.data or {}
    kind = str(data.get("kind") or "").strip()
    if kind not in KINDS:
        raise ApiError("INVALID_PROVIDER_KIND", "kind 必须是 chat / vision / tts / asr", 400)
    name = str(data.get("name") or "").strip()
    if not 1 <= len(name) <= 80:
        raise ApiError("INVALID_NAME", "name 长度必须在 1–80 之间", 400)
    if ProviderProfile.objects.filter(kind=kind, name=name).exists():
        raise ApiError("PROVIDER_EXISTS", f"{kind} 下已经存在同名 Provider", 409)
    base_url = validate_base_url(str(data.get("base_url") or ""))
    model = str(data.get("model") or "").strip()
    if not 1 <= len(model) <= 200:
        raise ApiError("INVALID_MODEL", "model 长度必须在 1–200 之间", 400)

    profile = ProviderProfile.objects.create(
        kind=kind,
        name=name,
        base_url=base_url,
        model=model,
        api_key=str(data.get("api_key") or ""),
        extra_json=data.get("extra") if isinstance(data.get("extra"), dict) else {},
        enabled=bool(data.get("enabled", True)),
        is_default=bool(data.get("is_default", False)),
    )
    if profile.is_default:
        _set_default(profile)
    elif not ProviderProfile.objects.filter(kind=kind, is_default=True).exists():
        _set_default(profile)
    return Response({"ok": True, "provider": _payload_for(profile, reveal=True)}, status=201)


@api_view(["GET", "PATCH", "PUT", "DELETE"])
def provider_detail(request, provider_id):
    profile = get_object_or_404(ProviderProfile, pk=provider_id)

    if request.method == "GET":
        reveal = str(request.query_params.get("reveal", "")).lower() in {"1", "true", "yes"}
        return Response({"ok": True, "provider": _payload_for(profile, reveal)})

    if request.method == "DELETE":
        others = ProviderProfile.objects.filter(kind=profile.kind).exclude(pk=profile.pk)
        if profile.is_default and others.exists():
            raise ApiError(
                "DEFAULT_PROVIDER",
                "这是默认 Provider，请先把同类型的其它 Provider 设为默认再删除。",
                400,
            )
        profile.delete()
        if others.exists() and not others.filter(is_default=True).exists():
            promoted = others.order_by("created_at").first()
            if promoted:
                _set_default(promoted)
        return Response({"ok": True, "deleted": str(provider_id)})

    data = request.data or {}
    if "name" in data:
        name = str(data["name"]).strip()
        if not 1 <= len(name) <= 80:
            raise ApiError("INVALID_NAME", "name 长度必须在 1–80 之间", 400)
        if ProviderProfile.objects.filter(kind=profile.kind, name=name).exclude(pk=profile.pk).exists():
            raise ApiError("PROVIDER_EXISTS", "同类型下已经存在同名 Provider", 409)
        profile.name = name
    if "base_url" in data:
        profile.base_url = validate_base_url(str(data["base_url"]))
    if "model" in data:
        model = str(data["model"]).strip()
        if not 1 <= len(model) <= 200:
            raise ApiError("INVALID_MODEL", "model 长度必须在 1–200 之间", 400)
        profile.model = model
    if "extra" in data:
        if not isinstance(data["extra"], dict):
            raise ApiError("INVALID_EXTRA", "extra 必须是 JSON 对象", 400)
        profile.extra_json = data["extra"]
    if "enabled" in data:
        profile.enabled = bool(data["enabled"])
    if "api_key" in data:
        raw = str(data["api_key"])
        if raw == "__CLEAR__":
            profile.api_key = ""
        elif raw != "":
            profile.api_key = raw
    if data.get("is_default"):
        _set_default(profile)
    profile.save()
    return Response({"ok": True, "provider": _payload_for(profile, reveal=True)})


@api_view(["POST"])
def provider_test(request, provider_id):
    from asgiref.sync import async_to_sync

    profile = get_object_or_404(ProviderProfile, pk=provider_id)
    result = async_to_sync(test_provider)(profile)
    return Response({"ok": result.get("ok", False), "result": result})


@api_view(["POST"])
def provider_seed(request):
    seed_from_env()
    return Response({"ok": True, "count": ProviderProfile.objects.count()})
