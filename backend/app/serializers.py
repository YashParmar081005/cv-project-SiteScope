"""MongoDB document → API response shapes."""
from __future__ import annotations


def file_url(asset_id: str | None) -> str | None:
    return f"/api/files/{asset_id}" if asset_id else None


def clean(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if not k.startswith("_")}
    out["id"] = doc["_id"]
    return out


def user_out(user: dict) -> dict:
    return {"id": user["_id"], "email": user["email"], "name": user["name"], "role": user["role"],
            "created_at": user["created_at"]}


def observation_out(obs: dict) -> dict:
    out = clean(obs)
    original = out.pop("original")
    out["image"] = {"url": file_url(original["asset_id"]), "width": original["width"], "height": original["height"],
                    "filename": original.get("filename")}
    out["thumbnail_url"] = file_url(out.pop("thumb_asset_id", None))
    return out


def analysis_out(analysis: dict | None) -> dict | None:
    if analysis is None:
        return None
    out = clean(analysis)
    out["steps"] = [s | {"image_url": file_url(s.get("asset_id"))} for s in analysis["steps"]]
    return out
