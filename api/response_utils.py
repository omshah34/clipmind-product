from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)


def normalize_model(model_cls: type[ModelT], payload: Any) -> dict[str, Any]:
    return model_cls.model_validate(payload).model_dump(mode="json")
